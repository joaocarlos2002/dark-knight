import re
from pathlib import Path

import pytest
from fake_gitlab import PREFIX, TOKEN, FakeGateway
from typer.testing import CliRunner

from qa_workbench.integrations.errors import NotAuthorizedError
from qa_workbench.integrations.gitlab import cli
from qa_workbench.integrations.guarded import GuardedGateway
from qa_workbench.integrations.http import GatewayRequest
from qa_workbench.main import app
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.policy import AutonomyMode
from qa_workbench.security.settings import SecuritySettings

runner = CliRunner()
URL = "https://gitlab.test/group/app"


def _guard(tmp_path: Path, **settings) -> ActionGuard:
    options = {"allowed_hosts": ("gitlab.test",), "mode": AutonomyMode.SEMI_AUTONOMOUS}
    return ActionGuard(SecuritySettings(**{**options, **settings}), AuditLog(tmp_path))


def _get(gateway: GuardedGateway, url: str):
    return gateway.get(GatewayRequest(url, headers={"PRIVATE-TOKEN": TOKEN}))


def test_an_authorized_host_is_read_and_audited(tmp_path) -> None:
    inner = FakeGateway({PREFIX + "/issues": []})
    gateway = GuardedGateway(inner, _guard(tmp_path), "GitLab")

    assert _get(gateway, "https://gitlab.test/api/v4/projects/x").status in (200, 404)

    entry = AuditLog(tmp_path).entries()[0]
    assert entry.kind == "action_allowed" and entry.actor == "gitlab-reader"
    assert TOKEN not in str(entry.data)  # the token travels in a header, never the log


def test_a_host_outside_the_scope_receives_nothing(tmp_path) -> None:
    inner = FakeGateway({})
    gateway = GuardedGateway(inner, _guard(tmp_path), "GitLab")

    with pytest.raises(NotAuthorizedError, match="outside the authorized hosts"):
        _get(gateway, "https://evil.example.com/api/v4/projects/x")

    assert inner.requests == []  # the token was never sent there


def test_the_rate_limit_applies_to_reads(tmp_path) -> None:
    gateway = GuardedGateway(
        FakeGateway({}), _guard(tmp_path, max_requests_per_minute=1), "GitLab"
    )

    _get(gateway, "https://gitlab.test/api/v4/a")
    with pytest.raises(NotAuthorizedError, match="Rate limit"):
        _get(gateway, "https://gitlab.test/api/v4/b")


def test_a_local_gitlab_is_always_in_scope(tmp_path) -> None:
    inner = FakeGateway({})
    gateway = GuardedGateway(inner, _guard(tmp_path, allowed_hosts=()), "GitLab")

    _get(gateway, "http://127.0.0.1:8080/api/v4/a")

    assert len(inner.requests) == 1


def test_cancelling_stops_reads(tmp_path) -> None:
    guard = _guard(tmp_path)
    guard.cancel("Ana", "stop")
    inner = FakeGateway({})

    with pytest.raises(NotAuthorizedError, match="cancelled"):
        _get(GuardedGateway(inner, guard, "GitLab"), "https://gitlab.test/api/v4/a")
    assert inner.requests == []


def test_a_reader_never_posts(tmp_path) -> None:
    gateway = GuardedGateway(FakeGateway({}), _guard(tmp_path), "GitLab")

    with pytest.raises(NotAuthorizedError, match="only sends GET"):
        gateway.post(GatewayRequest("https://gitlab.test/api/v4/a"))


# -- the command ---------------------------------------------------------------


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeGateway:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
    gateway = FakeGateway({PREFIX + "/issues": []})
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    created = runner.invoke(app, ["project", "create", "Demo", "--repository", URL])
    assert created.exit_code == 0, created.output
    return gateway


def test_the_command_refuses_a_host_the_project_does_not_allow(fake) -> None:
    result = runner.invoke(app, ["gitlab", "issues", "-p", "PROJ-001"])
    out = _plain(result.output)

    assert result.exit_code == 1 and "needs approval" in out
    assert "batman security approve APR-" in out and "--allow-host" in out
    assert fake.requests == []  # nothing, token included, left the machine


def test_the_command_reads_and_audits_once_the_host_is_allowed(fake) -> None:
    scope = ["security", "set", "-p", "PROJ-001", "--allow-host", "gitlab.test"]
    runner.invoke(app, [*scope, "--by", "Ana"])

    result = runner.invoke(app, ["gitlab", "issues", "-p", "PROJ-001"])

    assert result.exit_code == 0, result.output
    assert len(fake.requests) == 1
    audit = runner.invoke(app, ["security", "audit", "-p", "PROJ-001", "--verify"])
    assert "intact" in _plain(audit.output)


def test_an_explicit_url_to_another_host_is_also_refused(fake) -> None:
    scope = ["security", "set", "-p", "PROJ-001", "--allow-host", "gitlab.test"]
    runner.invoke(app, [*scope, "--by", "Ana"])

    result = runner.invoke(
        app,
        ["gitlab", "issues", "-p", "PROJ-001", "--url", "https://other.test/g/app"],
    )

    assert result.exit_code == 1 and "outside the authorized hosts" in _plain(
        result.output
    )
    assert fake.requests == []
