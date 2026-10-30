import re
from pathlib import Path

import pytest
from fake_ai import FakeHttp, answer, down, ok
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
