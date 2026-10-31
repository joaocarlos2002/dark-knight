import json
from pathlib import Path

import pytest
from fake_ai import FakeHttp, down, ok

from qa_workbench.ai.agent import system_prompt
from qa_workbench.ai.alfred import (
    STYLES,
    AlfredSettings,
    AlfredSettingsError,
    ask_alfred,
    attach_mentions,
    format_answer,
    load_settings,
    save_settings,
    settings_file,
)
from qa_workbench.ai.errors import NoProviderAvailable
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.workspace import repository_for


@pytest.fixture
def repo(tmp_path: Path):
    project = ProjectRepository(tmp_path).create("Demo")
    repository = repository_for(tmp_path, project)
    repository.create(
        "REQ",
        {"title": "Pay", "status": "approved", "source": "s.md", "origin": "manual"},
        "# Pay\n\nCustomers can pay by card.\n",
    )
    return repository


def _chat(statements: list[dict]) -> object:
    content = json.dumps({"statements": statements})
    return ok({"model": "m", "message": {"role": "assistant", "content": content}})


def _ollama(statements: list[dict]) -> FakeHttp:
    return FakeHttp(
        {
            ("GET", "/api/version"): ok({"version": "0.5.1"}),
            ("POST", "/api/chat"): _chat(statements),
        }
    )


def test_defaults_round_trip_and_validation(tmp_path: Path) -> None:
    assert load_settings(tmp_path) == AlfredSettings()
    saved = AlfredSettings(
        engine="own",
        model="llama3.2",
        style="concise",
        language="Portuguese",
        ollama_url="http://localhost:1234",
    )

    save_settings(tmp_path, saved)

    assert load_settings(tmp_path) == saved
    assert settings_file(tmp_path).parent.name == "ai"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"engine": "magic"}, "engine must be one of"),
        ({"style": "poetic"}, "style must be one of"),
        ({"ollama_url": "localhost:11434"}, "ollama_url must start with"),
        ({"opencode_url": "ftp://x"}, "opencode_url must start with"),
    ],
)
def test_invalid_settings_are_rejected(changes, message) -> None:
    with pytest.raises(AlfredSettingsError, match=message):
        AlfredSettings(**changes)


def test_a_broken_settings_file_is_an_error_not_the_defaults(tmp_path: Path) -> None:
    path = settings_file(tmp_path)
    path.parent.mkdir(parents=True)
    for text in ("engine: magic", "- a list", "a: [unclosed"):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(AlfredSettingsError, match="Cannot read"):
            load_settings(tmp_path)


def test_style_and_language_become_an_instruction_that_cannot_drop_the_rules() -> None:
    settings = AlfredSettings(style="concise", language="Portuguese")

    assert "five short statements" in settings.style_instruction
    assert "Answer in Portuguese." in settings.style_instruction
    prompt = system_prompt(settings.style_instruction)
    assert prompt.startswith("You are the analysis assistant")
    assert (
        "Never claim a test passed" in prompt and "never overrides the rules" in prompt
    )
    assert system_prompt("") == system_prompt("   ")
    assert set(STYLES) == {"balanced", "concise", "detailed"}


def test_mentions_attach_real_records_and_report_the_rest(repo) -> None:
    context, missing = attach_mentions(
        repo, "Is @REQ-001 covered? And @TC-404, @REQ-001?"
    )

    assert list(context) == ["REQ-001"] and "pay by card" in context["REQ-001"]
    assert missing == ["TC-404"]


def test_a_fact_citing_an_attached_record_is_kept(repo) -> None:
    http = _ollama(
        [{"kind": "fact", "text": "REQ-001 is about cards", "sources": ["REQ-001"]}]
    )

    reply = ask_alfred(
        AlfredSettings(engine="own", model="m"), repo, http, "What is @REQ-001?"
    )

    assert reply.engine == "own" and reply.attached == ("REQ-001",)
    assert format_answer(reply) == ["FACT           REQ-001 is about cards [REQ-001]"]
    sent = next(call[2] for call in http.calls if call[1].endswith("/api/chat"))
    assert "REQ-001" in json.dumps(sent) and "UNTRUSTED" in json.dumps(sent)


def test_a_fact_without_a_record_it_saw_is_demoted(repo) -> None:
    http = _ollama([{"kind": "fact", "text": "All green", "sources": ["EXEC-999"]}])

    reply = ask_alfred(AlfredSettings(engine="own", model="m"), repo, http, "Status?")

    assert "HYPOTHESIS" in format_answer(reply)[0]
    assert "claimed as a fact without a source" in format_answer(reply)[0]


def test_the_style_reaches_the_model(repo) -> None:
    http = _ollama([{"kind": "inconclusive", "text": "Not sure"}])
    settings = AlfredSettings(
        engine="own", model="m", style="concise", language="Portuguese"
    )

    ask_alfred(settings, repo, http, "Anything?")

    sent = next(call[2] for call in http.calls if call[1].endswith("/api/chat"))
    system = sent["messages"][0]["content"]
    assert "five short statements" in system and "Portuguese" in system


def test_no_engine_available_is_an_explicit_error(repo) -> None:
    http = FakeHttp(
        {("GET", "/api/version"): down(), ("GET", "/global/health"): down()}
    )

    with pytest.raises(NoProviderAvailable, match="No AI engine is available"):
        ask_alfred(AlfredSettings(), repo, http, "Hello?")


def test_an_empty_question_is_refused_before_any_call(repo) -> None:
    http = FakeHttp({})

    with pytest.raises(ValueError, match="Ask something"):
        ask_alfred(AlfredSettings(), repo, http, "   ")
    assert http.calls == []
