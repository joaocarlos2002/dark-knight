import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Static

from qa_workbench.ai import cli as ai_cli
from qa_workbench.ai.alfred import AlfredSettings, load_settings, save_settings
from qa_workbench.ai.http import JsonResponse, TransportFailure
from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.settings import SecuritySettings
from qa_workbench.security.settings import save_settings as save_security
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.agent_chat import AgentChat
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for


class Http:
    """A tiny Ollama: answers /api/version and /api/chat, or is down."""

    def __init__(self, statements=None, up: bool = True) -> None:
        self.statements = statements or [{"kind": "inconclusive", "text": "Not sure."}]
        self.up = up
        self.bodies: list[dict] = []

    def request(self, method, url, *, body=None, headers=None, timeout=30.0):
        if not self.up:
            raise TransportFailure("connection", "refused")
        if url.endswith("/api/version"):
            return JsonResponse(200, {"version": "0.5.1"}, {})
        if url.endswith("/global/health"):
            raise TransportFailure("connection", "refused")
        self.bodies.append(body)
        content = json.dumps({"statements": self.statements})
        message = {"role": "assistant", "content": content}
        return JsonResponse(200, {"model": "m", "message": message}, {})

    def stream_lines(self, *args, **kwargs):  # pragma: no cover - not used
        raise AssertionError("Alfred does not stream")


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo")


@pytest.fixture
def repo(tmp_path: Path, project):
    repository = repository_for(tmp_path, project)
    repository.create(
        "REQ",
        {"title": "Pay", "status": "approved", "source": "s.md", "origin": "manual"},
        "# Pay\n\nCustomers can pay by card.\n",
    )
    save_settings(repository.root, AlfredSettings(engine="own", model="m"))
    return repository


def _run(data_dir: Path, scenario, project=None, size=(140, 55)) -> None:
    async def runner() -> None:
        app = WorkbenchApp(
            project,
            preview_channel=PreviewChannel(data_dir / "preview"),
            data_dir=data_dir,
        )
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


async def _until(pilot, condition, tries: int = 100) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _chat(app: WorkbenchApp) -> AgentChat:
    return app.query_one("#page-ai-agent").query_one(AgentChat)


async def _ask(app, pilot, text: str) -> None:
    chat = _chat(app)
    chat.focus_input()
    chat.query_one("#chat-input", Input).value = text
    await pilot.press("enter")


def _spoken(app: WorkbenchApp) -> str:
    return _chat(app).transcript()


def test_without_a_project_alfred_says_so(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        summary = str(app.query_one("#alfred-summary", Static).render())
        assert "No project is open" in summary
        await _ask(app, pilot, "hello")
        await pilot.pause()
        assert "No project is open" in _spoken(app)

    _run(tmp_path, scenario)


def test_a_question_gets_a_typed_answer_without_blocking(
    tmp_path, project, repo, monkeypatch
) -> None:
    http = Http(
        [
            {"kind": "fact", "text": "REQ-001 is about cards", "sources": ["REQ-001"]},
            {"kind": "recommendation", "text": "Add a refund case"},
        ]
    )
    monkeypatch.setattr(ai_cli, "default_http", lambda: http)

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        assert "Engine: own" in str(app.query_one("#alfred-summary", Static).render())
        await _ask(app, pilot, "What is @REQ-001? And @TC-404?")
        await _until(pilot, lambda: "(engine: own)" in _spoken(app))
        said = _spoken(app)
        assert said.startswith("YOU")
        assert "FACT           REQ-001 is about cards [REQ-001]" in said
        assert "RECOMMENDATION Add a refund case" in said
        assert (
            "(attached: REQ-001)" in said
            and "not found, so not attached: TC-404" in said
        )
        assert not _chat(app).query_one("#chat-input", Input).disabled

    _run(tmp_path, scenario, project)


def test_an_unsupported_fact_is_shown_as_a_hypothesis(
    tmp_path, project, repo, monkeypatch
) -> None:
    http = Http([{"kind": "fact", "text": "All passed", "sources": ["EXEC-9"]}])
    monkeypatch.setattr(ai_cli, "default_http", lambda: http)

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await _ask(app, pilot, "How did it go?")
        await _until(pilot, lambda: "(engine: own)" in _spoken(app))
        assert "HYPOTHESIS" in _spoken(app) and "without a source" in _spoken(app)

    _run(tmp_path, scenario, project)


def test_no_engine_is_a_notice_not_a_fake_answer(
    tmp_path, project, repo, monkeypatch
) -> None:
    monkeypatch.setattr(ai_cli, "default_http", lambda: Http(up=False))

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await _ask(app, pilot, "Anyone there?")
        await _until(pilot, lambda: "NOTICE" in _spoken(app))
        assert "No AI engine is available" in _spoken(app)
        assert "ollama serve" in _spoken(app)
        assert not _chat(app).query_one("#chat-input", Input).disabled  # can try again

    _run(tmp_path, scenario, project)


def test_the_settings_form_saves_and_validates(tmp_path, project, repo) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert isinstance(app.screen, FormDialog)
        assert app.screen.query_one("#field-engine", Input).value == "own"

        app.screen.query_one("#field-engine", Input).value = "magic"
        await pilot.pause()
        app.screen.query_one("#submit", Button).press()
        await pilot.pause()
        await pilot.pause()
        error = str(app.screen.query_one("#form-error", Static).render())
        assert "engine must be one of" in error

        app.screen.query_one("#field-engine", Input).value = "opencode"
        app.screen.query_one("#field-style", Input).value = "concise"
        await pilot.pause()
        app.screen.query_one("#submit", Button).press()
        await _until(pilot, lambda: load_settings(repo.root).engine == "opencode")
        saved = load_settings(repo.root)
        assert saved.style == "concise" and saved.model == "m"
        await _until(
            pilot,
            lambda: (
                "Engine: opencode"
                in str(app.query_one("#alfred-summary", Static).render())
            ),
        )

    _run(tmp_path, scenario, project)


def test_clear_empties_the_conversation(tmp_path, project, repo, monkeypatch) -> None:
    monkeypatch.setattr(ai_cli, "default_http", lambda: Http())

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await _ask(app, pilot, "Hi")
        await _until(pilot, lambda: "(engine: own)" in _spoken(app))
        await pilot.press("ctrl+l")
        assert _spoken(app) == ""

    _run(tmp_path, scenario, project)


def test_an_archived_project_keeps_its_settings(tmp_path, project, repo) -> None:
    archived = ProjectRepository(tmp_path).archive(project.id)

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)

    _run(tmp_path, scenario, archived)


def test_the_chat_transcript_names_every_speaker() -> None:
    chat = AgentChat()
    chat.add_user("question")
    chat.add_assistant("answer")
    chat.add_notice("careful")

    text = chat.transcript()

    assert [s for s, _ in chat.lines] == ["YOU", "ALFRED", "NOTICE"]
    assert "YOU\n  question" in text and "ALFRED\n  answer" in text


class HostedHttp:
    """A tiny NVIDIA API: lists two models and answers a chat."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def request(self, method, url, *, body=None, headers=None, timeout=30.0):
        self.urls.append(url)
        if url.endswith("/models"):
            return JsonResponse(200, {"data": [{"id": "a/one"}, {"id": "b/two"}]}, {})
        content = json.dumps({"statements": [{"kind": "inconclusive", "text": "Hm."}]})
        return JsonResponse(200, {"choices": [{"message": {"content": content}}]}, {})

    def stream_lines(self, *args, **kwargs):  # pragma: no cover - not used
        raise AssertionError("Alfred does not stream")


def _hosted(repo, monkeypatch, *, allow: bool = True) -> HostedHttp:
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-0123456789abcdefghij")
    save_settings(repo.root, AlfredSettings(engine="nvidia", model="a/one"))
    if allow:
        save_security(
            repo.root, SecuritySettings(allowed_hosts=("integrate.api.nvidia.com",))
        )
    http = HostedHttp()
    monkeypatch.setattr(ai_cli, "default_http", lambda: http)
    return http


def test_the_model_picker_lists_the_models_and_saves_the_choice(
    tmp_path, project, repo, monkeypatch
) -> None:
    _hosted(repo, monkeypatch)

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await pilot.press("ctrl+g")
        await _until(pilot, lambda: isinstance(app.screen, ChoiceDialog))
        assert "remote" in str(app.screen.query_one("#dialog-message").render()).lower()
        await pilot.press("down", "enter")
        await _until(pilot, lambda: load_settings(repo.root).model == "b/two")
        assert "Model: b/two" in str(app.query_one("#alfred-summary", Static).render())

    _run(tmp_path, scenario, project)


def test_a_remote_answer_says_data_left_the_machine(
    tmp_path, project, repo, monkeypatch
) -> None:
    http = _hosted(repo, monkeypatch)

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await _ask(app, pilot, "hello")
        await _until(pilot, lambda: "engine: nvidia" in _spoken(app))
        assert "remote: data left this machine" in _spoken(app)
        assert any(url.endswith("/chat/completions") for url in http.urls)

    _run(tmp_path, scenario, project)


def test_a_host_that_is_not_allowed_is_a_notice_and_sends_nothing(
    tmp_path, project, repo, monkeypatch
) -> None:
    http = _hosted(repo, monkeypatch, allow=False)

    async def scenario(app, pilot) -> None:
        app.navigate("ai-agent")
        await pilot.pause()
        await _ask(app, pilot, "hello")
        await _until(pilot, lambda: "nothing was sent" in _spoken(app))
        assert "--allow-host integrate.api.nvidia.com" in _spoken(app)
        assert http.urls == []

    _run(tmp_path, scenario, project)
