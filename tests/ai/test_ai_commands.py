import re
from pathlib import Path

import pytest
from fake_ai import FakeHttp, FakeRunner, answer, claude_reply, down, ok
from typer.testing import CliRunner

from qa_workbench.ai import cli
from qa_workbench.main import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OPENCODE_URL", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_PATH", raising=False)
    # No real process: Claude Code is "not installed" unless a test says otherwise.
    monkeypatch.setattr(cli, "default_runner", lambda: FakeRunner(version=None))


def _serve(monkeypatch: pytest.MonkeyPatch, routes) -> FakeHttp:
    http = FakeHttp(routes)
    monkeypatch.setattr(cli, "default_http", lambda: http)
    return http


def _run(*args: str):
    result = runner.invoke(app, ["ai", *args])
    return result, _plain(result.output)


def _chat(content: str) -> dict:
    return {"model": "m", "message": {"role": "assistant", "content": content}}


def test_status_lists_each_engine_and_fails_when_none_is_up(monkeypatch) -> None:
    _serve(
        monkeypatch,
        {
            ("GET", "/api/version"): ok({"version": "0.5.1"}),
            ("GET", "/global/health"): down(),
        },
    )
    result, out = _run("status")
    assert result.exit_code == 0
    assert "ollama" in out and "available" in out and "opencode serve" in out

    _serve(
        monkeypatch,
        {("GET", "/api/version"): down(), ("GET", "/global/health"): down()},
    )
    assert _run("status")[0].exit_code == 1


def test_ask_answers_with_kinds_and_demotes_unsupported_facts(monkeypatch) -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    reply = answer(
        {"kind": "fact", "text": "Everything passed", "sources": ["EXEC-123"]},
        {"kind": "recommendation", "text": "Run the smoke suite"},
    )
    _serve(
        monkeypatch,
        {
            ("GET", "/api/version"): ok({"version": "0.5.1"}),
            ("POST", "/api/chat"): ok(_chat(reply)),
        },
    )

    result, out = _run(
        "ask", "Is it ready?", "-p", "PROJ-001", "--engine", "own", "--model", "m"
    )

    assert result.exit_code == 0, out
    assert "HYPOTHESIS" in out and "without a source" in out
    assert "RECOMMENDATION" in out and "not evidence" in out


def test_ask_fails_clearly_when_no_engine_is_available(monkeypatch) -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    _serve(
        monkeypatch,
        {("GET", "/api/version"): down(), ("GET", "/global/health"): down()},
    )

    result, out = _run("ask", "q", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "No AI engine is available" in out and "ollama serve" in out


def test_ask_reports_a_model_that_ignores_the_answer_format(monkeypatch) -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    _serve(
        monkeypatch,
        {
            ("GET", "/api/version"): ok({"version": "0.5.1"}),
            ("POST", "/api/chat"): ok(_chat("Sure! It all looks great.")),
        },
    )

    result, out = _run("ask", "q", "-p", "PROJ-001", "--engine", "own", "--model", "m")

    assert result.exit_code == 1 and "expected structure" in out


def test_ask_validates_engine_and_project(monkeypatch) -> None:
    _serve(monkeypatch, {})

    assert (
        "engine must be one of"
        in _run("ask", "q", "-p", "PROJ-001", "--engine", "x")[1]
    )
    result, out = _run("ask", "q", "-p", "PROJ-404")
    assert result.exit_code == 1 and "PROJ-404" in out


# -- the hosted NVIDIA engine ------------------------------------------------

KEY = "nvapi-0123456789abcdefghij"
HOST = "integrate.api.nvidia.com"
MODELS = ok({"data": [{"id": "meta/llama-3.1-8b-instruct"}, {"id": "a/b"}]})


def _nvidia_chat(content: str) -> dict:
    return {"model": "a/b", "choices": [{"message": {"content": content}}]}


def _project(allow: bool = True) -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    if allow:
        runner.invoke(
            app,
            ["security", "set", "-p", "PROJ-001", "--allow-host", HOST, "--by", "qa"],
        )


def _stored_text(tmp_path: Path) -> str:
    return "\n".join(
        f.read_text(encoding="utf-8", errors="ignore")
        for f in tmp_path.rglob("*")
        if f.is_file()
    )


def test_ask_nvidia_works_against_a_fake_server_and_says_it_is_remote(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    _project()
    reply = answer({"kind": "recommendation", "text": "Run the smoke suite"})
    http = _serve(
        monkeypatch,
        {
            ("GET", "/models"): MODELS,
            ("POST", "/chat/completions"): ok(_nvidia_chat(reply)),
        },
    )

    result, out = _run(
        "ask", "q", "-p", "PROJ-001", "--engine", "nvidia", "--model", "a/b"
    )

    assert result.exit_code == 0, out
    assert "RECOMMENDATION" in out and "leave this machine" in out
    assert http.calls[-1][2]["model"] == "a/b"
    assert KEY not in out and KEY not in _stored_text(tmp_path)


def test_ask_nvidia_with_a_host_that_is_not_allowed_sends_nothing(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    _project(allow=False)
    http = _serve(monkeypatch, {("GET", "/models"): MODELS})

    result, out = _run(
        "ask", "q", "-p", "PROJ-001", "--engine", "nvidia", "--model", "a/b"
    )

    assert result.exit_code == 1
    assert "nothing was sent" in out and f"--allow-host {HOST}" in out
    assert http.calls == [] and KEY not in out


def test_ask_nvidia_failures_name_the_endpoint_and_never_the_key(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    _project()
    _serve(monkeypatch, {("GET", "/models"): ok({}, 401)})

    result, out = _run(
        "ask", "q", "-p", "PROJ-001", "--engine", "nvidia", "--model", "a/b"
    )

    assert result.exit_code == 1
    assert "rejected the API key (HTTP 401)" in out and "/v1/models" in out
    assert KEY not in out


def test_auto_does_not_use_nvidia_even_when_it_is_the_only_engine_up(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    _project()
    http = _serve(
        monkeypatch,
        {
            ("GET", "/api/version"): down(),
            ("GET", "/global/health"): down(),
            ("GET", "/models"): MODELS,
        },
    )

    result, out = _run("ask", "q", "-p", "PROJ-001")

    assert result.exit_code == 1 and "No AI engine is available" in out
    assert not any(call[1].endswith("/models") for call in http.calls)


def test_models_lists_what_the_key_can_use(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    _project()
    _serve(monkeypatch, {("GET", "/models"): MODELS})

    result, out = _run("models", "-p", "PROJ-001")

    assert result.exit_code == 0, out
    assert "a/b" in out and "meta/llama-3.1-8b-instruct" in out
    assert "Remote engine" in out


def test_status_reports_nvidia_key_presence_and_reachability(monkeypatch) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    _project()
    http = _serve(
        monkeypatch,
        {
            ("GET", "/api/version"): ok({"version": "0.5.1"}),
            ("GET", "/global/health"): down(),
            ("GET", "/models"): MODELS,
        },
    )

    _, out = _run("status")
    assert "not checked" in out and "API key missing" in out
    assert not any(call[1].endswith("/models") for call in http.calls)

    monkeypatch.setenv("NVIDIA_API_KEY", KEY)
    _, out = _run("status", "-p", "PROJ-001")
    assert "nvidia    available" in out and "API key present" in out
    assert KEY not in out


# -- Claude Code ---------------------------------------------------------------


def _claude(monkeypatch, runner: FakeRunner) -> FakeRunner:
    monkeypatch.setattr(cli, "default_runner", lambda: runner)
    return runner


def _allow_anthropic() -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    runner.invoke(
        app,
        [
            "security",
            "set",
            "-p",
            "PROJ-001",
            "--allow-host",
            "api.anthropic.com",
            "--by",
            "qa",
        ],
    )


def test_ask_claude_runs_the_cli_and_says_it_is_remote(monkeypatch) -> None:
    _allow_anthropic()
    reply = answer({"kind": "recommendation", "text": "Run the smoke suite"})
    fake = _claude(monkeypatch, FakeRunner(claude_reply(reply)))

    result, out = _run("ask", "q", "-p", "PROJ-001", "--engine", "claude")

    assert result.exit_code == 0, out
    assert "RECOMMENDATION" in out and "leave this machine" in out
    assert len(fake.runs) == 1 and "--tools" in fake.runs[0][0]


def test_ask_claude_without_the_host_allowed_starts_nothing(monkeypatch) -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    fake = _claude(monkeypatch, FakeRunner(claude_reply("x")))

    result, out = _run("ask", "q", "-p", "PROJ-001", "--engine", "claude")

    assert result.exit_code == 1
    assert "nothing was sent" in out and "--allow-host api.anthropic.com" in out
    assert fake.runs == []


def test_auto_never_uses_claude_even_when_it_is_the_only_engine(monkeypatch) -> None:
    _allow_anthropic()
    fake = _claude(monkeypatch, FakeRunner(claude_reply("x")))
    _serve(
        monkeypatch,
        {("GET", "/api/version"): down(), ("GET", "/global/health"): down()},
    )

    result, out = _run("ask", "q", "-p", "PROJ-001")

    assert result.exit_code == 1 and "No AI engine is available" in out
    assert fake.runs == []


def test_status_and_models_show_claude(monkeypatch) -> None:
    _allow_anthropic()
    _claude(monkeypatch, FakeRunner())
    _serve(
        monkeypatch,
        {("GET", "/api/version"): down(), ("GET", "/global/health"): down()},
    )

    status, out = _run("status")
    assert status.exit_code == 0 and "claude    available" in out and "remote" in out

    _, models = _run("models", "-p", "PROJ-001", "--engine", "claude")
    assert "sonnet" in models and "opus" in models and "api.anthropic.com" in models
