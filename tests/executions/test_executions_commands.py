import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


@pytest.fixture(autouse=True)
def project(isolated_data: Path) -> None:
    assert _run("project", "create", "Demo")[0].exit_code == 0
    _run(
        "cases",
        "create",
        "Log in",
        "-p",
        "PROJ-001",
        "--objective",
        "x",
        "--step",
        "s",
        "--expected-result",
        "ok",
    )
    assert _run("review", "submit", "TC-001", "-p", "PROJ-001")[0].exit_code == 0
    done, _ = _run(
        "review",
        "decide",
        "TC-001",
        "-p",
        "PROJ-001",
        "--decision",
        "approved",
        "--reviewer",
        "Ana",
    )
    assert done.exit_code == 0


def _create(*extra: str):
    return _run(
        "executions",
        "create",
        "-p",
        "PROJ-001",
        "--type",
        "manual",
        "--executor",
        "Ana",
        "--environment",
        "staging",
        "--case",
        "TC-001",
        *extra,
    )


def _move(to: str, *extra: str):
    return _run("executions", "move", "EXEC-001", "-p", "PROJ-001", "--to", to, *extra)


def test_states_shows_the_whole_lifecycle() -> None:
    result, output = _run("executions", "states")

    assert result.exit_code == 0
    assert "created" in output and "-> cancelled, planned" in output
    assert "running" in output
    assert "finalized" in output and "(final)" in output
    assert "[result]" in output


def test_create_and_list() -> None:
    created, output = _create()

    listed, listing = _run("executions", "list", "-p", "PROJ-001")

    assert created.exit_code == 0
    assert "Created EXEC-001  created" in output
    assert (
        "EXEC-001  created" in listing and "manual" in listing and "TC-001" in listing
    )


def test_the_full_path_to_a_finalized_pass(tmp_path: Path) -> None:
    _create()
    shot = tmp_path / "shot.txt"
    shot.write_text("proof", encoding="utf-8")
    added, _ = _run(
        "evidence",
        "add",
        str(shot),
        "-p",
        "PROJ-001",
        "--source",
        "manual",
        "--description",
        "Dashboard",
    )

    steps = [
        _move("planned"),
        _move("running"),
        _move("passed", "--observed", "Dashboard shown", "--evidence", "EVD-001"),
        _move("finalized"),
    ]
    shown, body = _run("executions", "show", "EXEC-001", "-p", "PROJ-001")

    assert added.exit_code == 0
    assert [result.exit_code for result, _ in steps] == [0, 0, 0, 0]
    assert "EXEC-001 is now finalized." in steps[-1][1]
    assert "Dashboard shown" in body
    assert "- EVD-001" in body


def test_invalid_transitions_are_explained() -> None:
    _create()

    result, output = _move("running")

    assert result.exit_code == 1
    assert "Cannot move from created to running" in output
    assert "it can only move to: cancelled, planned" in output


def test_a_pass_without_evidence_is_refused() -> None:
    _create()
    _move("planned")
    _move("running")

    result, output = _move("passed", "--observed", "ok")

    assert result.exit_code == 1
    assert "a passed execution needs evidence" in output


def test_a_block_needs_a_reason_and_can_never_pass() -> None:
    _create()
    _move("planned")
    _move("running")

    refused, refused_output = _move("blocked")
    blocked, _ = _move("blocked", "--reason", "Environment down")
    pass_after, pass_output = _move("passed")

    assert refused.exit_code == 1
    assert "a blocked execution needs a reason" in refused_output
    assert blocked.exit_code == 0
    assert pass_after.exit_code == 1
    assert "Cannot move from blocked to passed" in pass_output


def test_approval_gates_the_start() -> None:
    _create("--requires-approval")
    _move("planned")

    skipped, skipped_output = _move("running")
    _move("awaiting_approval")
    unnamed, unnamed_output = _move("running")
    approved, _ = _move("running", "--approved-by", "Bruno")

    assert skipped.exit_code == 1
    assert "requires approval" in skipped_output
    assert unnamed.exit_code == 1
    assert "needs approved_by" in unnamed_output
    assert approved.exit_code == 0


def test_agent_automation_cannot_be_recorded_as_manual() -> None:
    result, output = _create("--automation-tool", "playwright")

    assert result.exit_code == 1
    assert "cannot name an automation tool" in output


def test_a_draft_case_cannot_be_executed() -> None:
    _run(
        "cases",
        "create",
        "Draft",
        "-p",
        "PROJ-001",
        "--objective",
        "x",
        "--step",
        "s",
        "--expected-result",
        "ok",
    )

    result, output = _run(
        "executions",
        "create",
        "-p",
        "PROJ-001",
        "--type",
        "manual",
        "--executor",
        "Ana",
        "--environment",
        "staging",
        "--case",
        "TC-002",
    )

    assert result.exit_code == 1
    assert "TC-002 is draft; only an active test case can be executed" in output


def test_an_unknown_target_state_is_refused() -> None:
    _create()

    result, output = _move("done")

    assert result.exit_code == 1
    assert "Unknown state 'done'" in output


def test_an_unknown_execution_is_reported() -> None:
    result, output = _run("executions", "show", "EXEC-404", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "EXEC-404 was not found" in output


def test_an_archived_project_cannot_receive_executions() -> None:
    _run("project", "archive", "PROJ-001")

    result, output = _create()

    assert result.exit_code == 1
    assert "PROJ-001 is archived and cannot be changed" in output
