import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_security_checks import SECURE, Server
from typer.testing import CliRunner

from qa_workbench.integrations.http import GatewayError
from qa_workbench.main import app
from qa_workbench.sectest import authorization as auth
from qa_workbench.sectest import cli
from qa_workbench.sectest.checks import CHECKS
from qa_workbench.sectest.records import SEC_SCHEMA, save_run
from qa_workbench.sectest.runner import run_checks
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, Cancelled, RateLimitExceeded
from qa_workbench.security.settings import SecuritySettings
from qa_workbench.storage.errors import RecordFinalizedError
from qa_workbench.storage.repository import MarkdownRepository

KNOWN = frozenset(CHECKS)
URL = "https://staging.example.com/"
NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


def _grant(root: Path, **overrides):
    options = dict(
        authorized_by="Ana", purpose="release 1.4 hardening",
        hosts=("staging.example.com",), checks=tuple(CHECKS), known_checks=KNOWN,
        days=1, now=NOW,
    )  # fmt: skip
    return auth.grant(root, **{**options, **overrides})


def _guard(root: Path, **settings) -> ActionGuard:
    options = {"allowed_hosts": ("staging.example.com",), **settings}
    return ActionGuard(SecuritySettings(**options), AuditLog(root))


# -- authorization ---------------------------------------------------------------


def test_grant_load_revoke_and_audit(tmp_path: Path) -> None:
    granted = _grant(tmp_path)

    assert auth.load(tmp_path) == granted
    assert [e.kind for e in AuditLog(tmp_path).entries()] == [
        "security_tests_authorized"
    ]
    assert auth.revoke(tmp_path, by="Ana") is True
    assert auth.load(tmp_path) is None and auth.revoke(tmp_path, by="Ana") is False
    assert AuditLog(tmp_path).entries()[-1].kind == "security_tests_revoked"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"authorized_by": " "}, "who authorizes"),
        ({"purpose": ""}, "what the tests are for"),
        ({"hosts": ()}, "at least one host"),
        ({"hosts": ("*.example.com",)}, "one exact host"),
        ({"hosts": (".example.com",)}, "one exact host"),
        ({"checks": ()}, "at least one check"),
        ({"checks": ("sqlmap",)}, "unknown check"),
        ({"days": 0}, "at most 30"),
        ({"days": 90}, "at most 30"),
    ],
)
def test_invalid_authorizations_are_refused_and_nothing_is_written(
    tmp_path: Path, overrides, message
) -> None:
    with pytest.raises(auth.NotAuthorized, match=message):
        _grant(tmp_path, **overrides)
    assert auth.load(tmp_path) is None


def test_every_requirement_for_a_check_is_enforced(tmp_path: Path) -> None:
    granted = _grant(tmp_path, checks=("headers",))
    settings = SecuritySettings(allowed_hosts=("staging.example.com",))

    auth.require(granted, settings, URL, "headers", now=NOW)
    cases = [
        (None, settings, URL, "headers", NOW, "No security-test authorization"),
        (granted, settings, URL, "headers", NOW + timedelta(days=2), "expired"),
        (
            granted,
            settings,
            "https://prod.example.com/",
            "headers",
            NOW,
            "not in the authorized hosts",
        ),
        (granted, SecuritySettings(), URL, "headers", NOW, "allowed hosts"),
        (granted, settings, URL, "cors", NOW, "was not authorized"),
    ]
    for authorization, config, url, check, now, message in cases:
        with pytest.raises(auth.NotAuthorized, match=message):
            auth.require(authorization, config, url, check, now=now)


def test_a_damaged_authorization_file_fails_loudly(tmp_path: Path) -> None:
    path = auth.path_of(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("authorized_by: Ana", encoding="utf-8")

    with pytest.raises(auth.NotAuthorized, match="damaged"):
        auth.load(tmp_path)


# -- runner ------------------------------------------------------------------------


def test_run_is_all_or_nothing_before_the_first_request(tmp_path: Path) -> None:
    _grant(tmp_path, checks=("headers",))
    server = Server({"*": (200, SECURE)})

    with pytest.raises(auth.NotAuthorized, match="'cors' was not authorized"):
        run_checks(
            url=URL, checks=("headers", "cors"), gateway=server,
            authorization=auth.load(tmp_path), guard=_guard(tmp_path), now=NOW,
        )  # fmt: skip

    assert server.requests == []


def test_unknown_checks_and_unauthorized_protected_paths_are_refused(
    tmp_path: Path,
) -> None:
    _grant(tmp_path)
    kwargs = dict(
        gateway=Server(),
        authorization=auth.load(tmp_path),
        guard=_guard(tmp_path),
        now=NOW,
    )

    with pytest.raises(auth.NotAuthorized, match="Unknown check"):
        run_checks(url=URL, checks=("sqlmap",), **kwargs)  # type: ignore[arg-type]
    assert kwargs["gateway"].requests == []  # type: ignore[attr-defined]


def test_a_run_reports_confirmed_findings_and_audits_every_check(
    tmp_path: Path,
) -> None:
    _grant(tmp_path, checks=("headers", "info-disclosure"))
    guard = _guard(tmp_path)
    server = Server({"*": (200, {"Server": "nginx/1.18.0"})})

    run = run_checks(
        url=URL, checks=("headers", "info-disclosure"), gateway=server,
        authorization=auth.load(tmp_path), guard=guard, now=NOW,
    )  # fmt: skip

    assert run.ok and any(f.confirmed for f in run.findings)
    kinds = [e.kind for e in guard.audit.entries()]
    assert kinds.count("security_check_started") == 2
    assert kinds.count("security_check_finished") == 2
    assert "action_allowed" in kinds


def test_an_unreachable_target_is_an_error_not_an_empty_pass(tmp_path: Path) -> None:
    _grant(tmp_path, checks=("headers",))
    server = Server()
    server.failure = GatewayError("connection refused")

    run = run_checks(
        url=URL, checks=("headers",), gateway=server,
        authorization=auth.load(tmp_path), guard=_guard(tmp_path), now=NOW,
    )  # fmt: skip

    assert not run.ok and run.checks[0].status == "error"
    assert "connection refused" in run.checks[0].error and run.findings == []


def test_the_rate_limit_and_cancellation_stop_the_run(tmp_path: Path) -> None:
    _grant(tmp_path, checks=("headers", "cors"))
    limited = _guard(tmp_path, max_requests_per_minute=1)

    with pytest.raises(RateLimitExceeded):
        run_checks(
            url=URL, checks=("headers", "cors"), gateway=Server(),
            authorization=auth.load(tmp_path), guard=limited, now=NOW,
        )  # fmt: skip

    cancelled = _guard(tmp_path)
    cancelled.cancel("Ana", "stop")
    with pytest.raises(Cancelled):
        run_checks(
            url=URL, checks=("headers",), gateway=Server(),
            authorization=auth.load(tmp_path), guard=cancelled, now=NOW,
        )  # fmt: skip


# -- records --------------------------------------------------------------------------


def test_saved_run_is_sealed_sanitized_and_never_claims_security(
    tmp_path: Path,
) -> None:
    root = tmp_path / "p"
    _grant(root, checks=("headers", "info-disclosure"))
    run = run_checks(
        url=URL + "?api_key=abc123456", checks=("headers", "info-disclosure"),
        gateway=Server({"*": (200, {"Server": "nginx/1.18.0"})}),
        authorization=auth.load(root), guard=_guard(root), now=NOW,
    )  # fmt: skip
    repository = MarkdownRepository(root, [SEC_SCHEMA])

    record = save_run(repository, run)

    assert (
        record.metadata["status"] == "completed" and record.metadata["confirmed"] >= 1
    )
    assert "abc123456" not in record.body
    assert "not a penetration test" in record.body and "not an OWASP" in record.body
    assert "## Confirmed findings" in record.body and "## Hypotheses" in record.body
    with pytest.raises(RecordFinalizedError):
        repository.update(record.id, {"confirmed": 0})


def test_an_incomplete_run_is_saved_as_incomplete(tmp_path: Path) -> None:
    root = tmp_path / "p"
    _grant(root, checks=("headers",))
    server = Server()
    server.failure = GatewayError("timed out")
    run = run_checks(
        url=URL, checks=("headers",), gateway=server,
        authorization=auth.load(root), guard=_guard(root), now=NOW,
    )  # fmt: skip

    record = save_run(MarkdownRepository(root, [SEC_SCHEMA]), run)

    assert record.metadata["status"] == "incomplete" and "ERROR" in record.body


# -- commands ------------------------------------------------------------------

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "d"))
    runner.invoke(app, ["project", "create", "Demo"])


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


@pytest.mark.usefixtures("project")
def test_commands_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server({"*": (200, {"Server": "nginx/1.18.0"})})
    monkeypatch.setattr(cli, "default_gateway", lambda: server)

    refused, out = _run("security-tests", "run", URL, "-p", "PROJ-001")
    assert refused.exit_code == 1 and "No security-test authorization" in out
    assert server.requests == []
    assert "Nothing can run" in _run("security-tests", "status", "-p", "PROJ-001")[1]

    granted, out = _run(
        "security-tests", "authorize", "-p", "PROJ-001", "--by", "Ana",
        "--purpose", "hardening", "--host", "staging.example.com", "--days", "1",
    )  # fmt: skip
    assert granted.exit_code == 0, out
    assert "valid" in _run("security-tests", "status", "-p", "PROJ-001")[1]

    no_scope, out = _run("security-tests", "run", URL, "-p", "PROJ-001")
    assert no_scope.exit_code == 1 and "project's allowed hosts" in out

    _run(
        "security",
        "set",
        "-p",
        "PROJ-001",
        "--allow-host",
        "staging.example.com",
        "--by",
        "Ana",
    )
    done, out = _run(
        "security-tests", "run", URL, "-p", "PROJ-001", "--check", "headers"
    )
    assert done.exit_code == 0, out
    assert "Saved SEC-001" in out and "CONFIRMED" in out
    assert "confirmed" in _run("security-tests", "list", "-p", "PROJ-001")[1]
    assert (
        "not a penetration test"
        in _run("security-tests", "show", "SEC-001", "-p", "PROJ-001")[1]
    )

    assert (
        "revoked"
        in _run("security-tests", "revoke", "-p", "PROJ-001", "--by", "Ana")[1]
    )
    assert _run("security-tests", "run", URL, "-p", "PROJ-001")[0].exit_code == 1
    assert "intact" in _run("security", "audit", "-p", "PROJ-001", "--verify")[1]


@pytest.mark.usefixtures("project")
def test_unreachable_target_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    server = Server()
    server.failure = GatewayError("connection refused")
    monkeypatch.setattr(cli, "default_gateway", lambda: server)
    _run(
        "security-tests", "authorize", "-p", "PROJ-001", "--by", "Ana",
        "--purpose", "x", "--host", "staging.example.com", "--check", "headers",
    )  # fmt: skip
    _run(
        "security",
        "set",
        "-p",
        "PROJ-001",
        "--allow-host",
        "staging.example.com",
        "--by",
        "Ana",
    )

    result, out = _run(
        "security-tests", "run", URL, "-p", "PROJ-001", "--check", "headers"
    )

    assert result.exit_code == 1 and "ERROR" in out and "connection refused" in out


@pytest.mark.usefixtures("project")
def test_invalid_authorize_and_unknown_project_are_reported() -> None:
    bad = _run("security-tests", "authorize", "-p", "PROJ-001", "--by", "Ana",
               "--purpose", "x", "--host", "*.example.com")  # fmt: skip
    assert bad[0].exit_code == 1 and "one exact host" in bad[1]
    assert _run("security-tests", "status", "-p", "PROJ-404")[0].exit_code == 1
