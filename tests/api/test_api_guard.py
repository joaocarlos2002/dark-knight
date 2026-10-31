import re
from pathlib import Path

import pytest
from fake_transport import FakeTransport, reply
from typer.testing import CliRunner

from qa_workbench.api import cli
from qa_workbench.api.errors import ApiNotAuthorized
from qa_workbench.api.guarded import GuardedTransport, category_for
from qa_workbench.api.transport import PreparedRequest
from qa_workbench.main import app
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, is_loopback
from qa_workbench.security.policy import AutonomyMode, Category
from qa_workbench.security.settings import SecuritySettings

runner = CliRunner()


def _guard(tmp_path: Path, **settings) -> ActionGuard:
    options = {"allowed_hosts": ("api.test",), "mode": AutonomyMode.SEMI_AUTONOMOUS}
    return ActionGuard(SecuritySettings(**{**options, **settings}), AuditLog(tmp_path))


def _send(transport: GuardedTransport, method: str, url: str):
    return transport.send(PreparedRequest(method, url))


@pytest.mark.parametrize(
    ("method", "category"),
    [
        ("GET", Category.READ),
        ("head", Category.READ),
        ("OPTIONS", Category.READ),
        ("POST", Category.ROUTINE),
        ("PUT", Category.ROUTINE),
        ("PATCH", Category.ROUTINE),
        ("DELETE", Category.DATA_CHANGE),
    ],
)
def test_what_a_request_does_decides_its_category(method, category) -> None:
    assert category_for(method) is category


def test_an_authorized_host_is_reached_and_the_request_is_audited(tmp_path) -> None:
    inner = FakeTransport(lambda r: reply(200, {"ok": True}))
    transport = GuardedTransport(inner, _guard(tmp_path))

    response = _send(transport, "GET", "https://api.test/me?api_key=abc123456")

    assert response.status == 200 and len(inner.requests) == 1
    entry = AuditLog(tmp_path).entries()[0]
    assert entry.kind == "action_allowed" and entry.actor == "api-runner"
    assert "abc123456" not in str(entry.data)  # query credentials never reach the log


def test_a_host_outside_the_scope_is_not_reached(tmp_path) -> None:
    inner = FakeTransport(lambda r: reply(200, {}))
    transport = GuardedTransport(inner, _guard(tmp_path))

    with pytest.raises(ApiNotAuthorized, match="outside the authorized hosts"):
        _send(transport, "GET", "https://prod.example.com/users")

    assert inner.requests == []
    assert AuditLog(tmp_path).entries()[-1].kind == "approval_requested"


def test_deleting_always_asks_even_on_an_authorized_host(tmp_path) -> None:
    inner = FakeTransport(lambda r: reply(204))
    transport = GuardedTransport(inner, _guard(tmp_path))

    with pytest.raises(ApiNotAuthorized, match="needs approval"):
        _send(transport, "DELETE", "https://api.test/users/7")

    assert inner.requests == []


def test_creating_asks_only_in_assisted_mode(tmp_path) -> None:
    inner = FakeTransport(lambda r: reply(201, {}))
    assisted = GuardedTransport(
        inner, _guard(tmp_path / "a", mode=AutonomyMode.ASSISTED)
    )

    with pytest.raises(ApiNotAuthorized, match="asks before every change"):
        _send(assisted, "POST", "https://api.test/users")
    assert inner.requests == []

    semi = GuardedTransport(inner, _guard(tmp_path / "b"))
    assert _send(semi, "POST", "https://api.test/users").status == 201


def test_an_approved_delete_goes_through_once(tmp_path) -> None:
    guard = _guard(tmp_path)
    inner = FakeTransport(lambda r: reply(204))
    transport = GuardedTransport(inner, guard)
    with pytest.raises(ApiNotAuthorized):
        _send(transport, "DELETE", "https://api.test/users/7")
    guard.book.decide(guard.book.pending()[0].request_id, approve=True, by="Ana")

    assert _send(transport, "DELETE", "https://api.test/users/7").status == 204
    with pytest.raises(ApiNotAuthorized):  # the approval was single-use
        _send(transport, "DELETE", "https://api.test/users/7")


def test_the_rate_limit_applies_to_api_requests(tmp_path) -> None:
    transport = GuardedTransport(
        FakeTransport(lambda r: reply(200, {})),
        _guard(tmp_path, max_requests_per_minute=1),
    )

    _send(transport, "GET", "https://api.test/a")
    with pytest.raises(ApiNotAuthorized, match="Rate limit"):
        _send(transport, "GET", "https://api.test/b")


def test_a_local_server_is_always_in_scope(tmp_path) -> None:
    inner = FakeTransport(lambda r: reply(200, {}))
    transport = GuardedTransport(inner, _guard(tmp_path, allowed_hosts=()))

    assert _send(transport, "GET", "http://127.0.0.1:8000/health").status == 200
    assert _send(transport, "GET", "http://localhost/x").status == 200
    assert is_loopback("http://[::1]:80/")
    assert not is_loopback("https://localhost.evil.test")


def test_cancelling_stops_api_requests(tmp_path) -> None:
    guard = _guard(tmp_path)
    guard.cancel("Ana", "stop")
    inner = FakeTransport(lambda r: reply(200, {}))

    with pytest.raises(ApiNotAuthorized, match="cancelled"):
        _send(GuardedTransport(inner, guard), "GET", "https://api.test/a")
    assert inner.requests == []


# -- the command ---------------------------------------------------------------


@pytest.fixture
def project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeTransport:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    assert runner.invoke(app, ["project", "create", "Demo"]).exit_code == 0
    fake = FakeTransport(lambda r: reply(200, {"ok": True}))
    monkeypatch.setattr(cli, "default_transport", lambda: fake)
    return fake


def _definition(tmp_path: Path, host: str) -> str:
    path = tmp_path / "t.yaml"
    path.write_text(
        f"name: T\nbase_url: https://{host}\nsteps:\n  - name: ping\n    url: /ping\n"
        "    expect: {status: 200}\n",
        encoding="utf-8",
    )
    return str(path)


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_the_command_refuses_an_unauthorized_host_and_says_how_to_continue(
    tmp_path, project
) -> None:
    definition = _definition(tmp_path, "prod.example.com")

    result = runner.invoke(app, ["api", "run", definition, "-p", "PROJ-001"])
    out = _plain(result.output)

    assert result.exit_code == 1 and "ERROR" in out
    assert "needs approval" in out and "batman security approve APR-" in out
    assert project.requests == []  # nothing was sent


def test_the_command_runs_once_the_host_is_allowed(tmp_path, project) -> None:
    scope = ["security", "set", "-p", "PROJ-001", "--allow-host", "api.test"]
    runner.invoke(app, [*scope, "--by", "Ana"])

    result = runner.invoke(
        app, ["api", "run", _definition(tmp_path, "api.test"), "-p", "PROJ-001"]
    )

    assert result.exit_code == 0, result.output
    assert len(project.requests) == 1
    audit = runner.invoke(app, ["security", "audit", "-p", "PROJ-001", "--verify"])
    assert "intact" in _plain(audit.output)
