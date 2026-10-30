import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, ApprovalRequired
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import load_settings
from qa_workbench.workspace import open_repository

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    assert runner.invoke(app, ["project", "create", "Demo"]).exit_code == 0


def _run(*args: str):
    result = runner.invoke(app, ["security", *args])
    return result, _plain(result.output)


def test_default_settings_are_the_safest() -> None:
    result, out = _run("show", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "mode: assisted" in out and "every external host needs approval" in out


def test_settings_change_is_validated_saved_and_audited() -> None:
    result, out = _run(
        "set", "-p", "PROJ-001", "--mode", "semi_autonomous",
        "--allow-host", "staging.example.com", "--rate", "10", "--by", "Ana",
    )  # fmt: skip

    assert result.exit_code == 0, out
    shown = _run("show", "-p", "PROJ-001")[1]
    assert "mode: semi_autonomous" in shown and "staging.example.com" in shown
    assert "max requests per minute: 10" in shown
    audit = _run("audit", "-p", "PROJ-001")[1]
    assert "settings_changed" in audit and "Ana" in audit


@pytest.mark.parametrize(
    "args",
    [
        ["--mode", "yolo", "--by", "Ana"],
        ["--allow-host", "*", "--by", "Ana"],
        ["--rate", "0"],
        ["--mode", "assisted"],  # missing --by
    ],
)
def test_invalid_changes_are_refused(args: list[str]) -> None:
    result, out = _run("set", "-p", "PROJ-001", *args)

    assert result.exit_code == 1 and out.startswith("Error")
    assert "mode: assisted" in _run("show", "-p", "PROJ-001")[1]


def test_approval_flow_from_request_to_use() -> None:
    root = open_repository("PROJ-001").root
    guard = ActionGuard(load_settings(root), AuditLog(root))
    action = ActionRequest("post comment", Category.EXTERNAL_COMMENT, "Result for #7")
    with pytest.raises(ApprovalRequired) as asked:
        guard.authorize(action)
    request_id = asked.value.request_id

    assert request_id in _run("approvals", "-p", "PROJ-001")[1]
    result, out = _run("approve", request_id, "-p", "PROJ-001", "--by", "Ana")
    assert result.exit_code == 0 and "approved by Ana" in out
    assert "No approval requests" in _run("approvals", "-p", "PROJ-001")[1]

    guard.authorize(action)
    listed = _run("approvals", "-p", "PROJ-001", "--all")[1]
    assert "used" in listed
    assert "intact: 3 entries" in _run("audit", "-p", "PROJ-001", "--verify")[1]


def test_denial_needs_a_reason_and_double_decisions_fail() -> None:
    root = open_repository("PROJ-001").root
    guard = ActionGuard(load_settings(root), AuditLog(root))
    with pytest.raises(ApprovalRequired) as asked:
        guard.authorize(ActionRequest("deploy", Category.PRODUCTION_WRITE))
    request_id = asked.value.request_id

    assert (
        _run("deny", request_id, "-p", "PROJ-001", "--by", "Ana", "--reason", "")[
            0
        ].exit_code
        == 1
    )
    ok = _run(
        "deny", request_id, "-p", "PROJ-001", "--by", "Ana", "--reason", "too risky"
    )
    assert ok[0].exit_code == 0
    again = _run("approve", request_id, "-p", "PROJ-001", "--by", "Bob")
    assert again[0].exit_code == 1 and "already denied" in again[1]
    assert (
        _run("approve", "APR-nope", "-p", "PROJ-001", "--by", "Bob")[0].exit_code == 1
    )


def test_a_tampered_audit_log_is_reported() -> None:
    root = open_repository("PROJ-001").root
    log = AuditLog(root)
    log.append("one", "ana", {})
    log.append("two", "ana", {})
    log.path.write_text(
        log.path.read_text(encoding="utf-8").replace("two", "TWO"), encoding="utf-8"
    )

    result, out = _run("audit", "-p", "PROJ-001", "--verify")

    assert result.exit_code == 1 and "was changed" in out


def test_unknown_project_is_reported() -> None:
    result, out = _run("show", "-p", "PROJ-404")

    assert result.exit_code == 1 and "PROJ-404" in out
