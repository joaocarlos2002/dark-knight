import re
from pathlib import Path

import pytest
from fake_transport import FakeTransport, reply, unreachable
from typer.testing import CliRunner

from qa_workbench.api import cli
from qa_workbench.api.errors import UnsafeToPersistError
from qa_workbench.api.models import Exchange, FlowResult, StepResult
from qa_workbench.api.records import API_SCHEMA, render, save_flow
from qa_workbench.main import app
from qa_workbench.storage.errors import RecordFinalizedError
from qa_workbench.storage.repository import MarkdownRepository

runner = CliRunner()

DEFINITION = """
name: Users API
base_url: https://api.test
steps:
  - name: login
    method: POST
    url: /login
    json: {user: ada@example.com}
    auth: {type: bearer, env: API_TOKEN}
    expect: {status: 200}
    extract:
      sid: {path: $.session, secret: true}
  - name: profile
    url: /me
    headers: {X-Session: "{{sid}}"}
    expect: {status: 200, json_equals: {"$.name": ada}}
"""


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("API_TOKEN", "tok-1234567890abcdef")
    return tmp_path


@pytest.fixture
def project(isolated: Path) -> None:
    assert runner.invoke(app, ["project", "create", "Demo"]).exit_code == 0


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


def _serve(monkeypatch: pytest.MonkeyPatch, handler) -> FakeTransport:
    transport = FakeTransport(handler)
    monkeypatch.setattr(cli, "default_transport", lambda: transport)
    return transport


def _definition(tmp_path: Path, text: str = DEFINITION) -> str:
    path = tmp_path / "users.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _ok(request):
    if request.url.endswith("/login"):
        return reply(200, {"session": "sess-value-424242", "mail": "ada@example.com"})
    return reply(200, {"name": "ada", "echo": "sess-value-424242"})


@pytest.mark.usefixtures("project")
def test_run_saves_a_sanitized_result_and_show_prints_it(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    _serve(monkeypatch, _ok)

    result, out = _run("api", "run", _definition(isolated), "-p", "PROJ-001")

    assert result.exit_code == 0, out
    assert "PASSED: saved as API-001" in out
    saved = _run("api", "show", "API-001", "-p", "PROJ-001")[1]
    for secret in ("tok-1234567890abcdef", "sess-value-424242", "example.com"):
        assert secret not in saved
    assert "[REDACTED]" in saved and "profile" in saved
    assert "API-001" in _run("api", "list", "-p", "PROJ-001")[1]


@pytest.mark.usefixtures("project")
def test_failed_check_exits_nonzero_and_still_saves_the_evidence(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    _serve(monkeypatch, lambda r: reply(500, {"error": "boom"}))

    result, out = _run("api", "run", _definition(isolated), "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "FAILED" in out and "status" in out and "saved as API-001" in out


@pytest.mark.usefixtures("project")
def test_unreachable_server_is_an_error_status(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    _serve(monkeypatch, unreachable)

    result, out = _run("api", "run", _definition(isolated), "-p", "PROJ-001")

    assert result.exit_code == 1 and "ERROR" in out and "connection refused" in out


@pytest.mark.usefixtures("project")
def test_invalid_definition_stops_before_any_request(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    transport = _serve(monkeypatch, _ok)

    result, out = _run("api", "run", _definition(isolated, "name: x"), "-p", "PROJ-001")

    assert result.exit_code == 1 and "not a valid API test" in out
    assert transport.requests == []


def test_unknown_project_is_reported(isolated: Path) -> None:
    result, out = _run("api", "run", _definition(isolated), "-p", "PROJ-404")

    assert result.exit_code == 1 and "PROJ-404" in out


@pytest.mark.usefixtures("project")
def test_empty_list_says_so() -> None:
    assert "No API results" in _run("api", "list", "-p", "PROJ-001")[1]


def _repository(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "records", [API_SCHEMA])


def _flow(response_body: str) -> FlowResult:
    exchange = Exchange(
        "GET", "https://api.test/x", {}, "", 200, {}, response_body, 5.0
    )
    return FlowResult(
        "Leaky", "https://api.test", (StepResult("s", "passed", (), exchange),)
    )


def test_persistence_refuses_output_that_still_holds_a_credential(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)

    with pytest.raises(UnsafeToPersistError, match="nothing was saved"):
        save_flow(repository, _flow('{"note": "password=hunter22"}'))

    assert repository.record_ids("API") == []


def test_saved_results_are_sealed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    record = save_flow(repository, _flow('{"ok": true}'))

    with pytest.raises(RecordFinalizedError):
        repository.update(record.id, {"title": "changed"})
    assert "Leaky" in render(_flow("{}"))
