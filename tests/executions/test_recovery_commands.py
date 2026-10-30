import re
from datetime import datetime, timedelta
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


def _x(*args: str):
    """Run an `executions` subcommand for EXEC-001 in PROJ-001."""
    return _run("executions", args[0], "EXEC-001", "-p", "PROJ-001", *args[1:])


@pytest.fixture(autouse=True)
def running_execution(isolated_data: Path) -> None:
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
    _run("review", "submit", "TC-001", "-p", "PROJ-001")
    _run(
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
    _run(
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
    )
    _x("move", "--to", "planned")
    assert _x("move", "--to", "running")[0].exit_code == 0


def test_steps_are_recorded_one_at_a_time() -> None:
    started, started_output = _x("step-start", "--number", "1", "--action", "Open")
    finished, finished_output = _x(
        "step-finish", "--number", "1", "--outcome", "passed", "--observed", "ok"
    )
    shown, body = _x("show")

    assert started.exit_code == 0
    assert "EXEC-001 step 1 started." in started_output
    assert finished.exit_code == 0
    assert "EXEC-001 step 1: passed." in finished_output
    assert "1. Open - passed: ok" in body


def test_step_mistakes_are_explained() -> None:
    out_of_order, order_output = _x("step-start", "--number", "2", "--action", "x")
    _x("step-start", "--number", "1", "--action", "Open")
    twice, twice_output = _x("step-start", "--number", "2", "--action", "x")
    unclassified, failed_output = _x(
        "step-finish", "--number", "1", "--outcome", "failed", "--observed", "500"
    )

    assert out_of_order.exit_code == 1
    assert "next step is number 1, not 2" in order_output
    assert twice.exit_code == 1
    assert "Step 1 is still in progress" in twice_output
    assert unclassified.exit_code == 1
    assert "failed step 1 needs a failure_type" in failed_output


def test_a_failure_is_classified() -> None:
    unclassified, output = _x("move", "--to", "failed", "--observed", "Error 500")
    classified, _ = _x(
        "move",
        "--to",
        "failed",
        "--observed",
        "Error 500",
        "--failure-type",
        "infrastructure",
    )
    bad, bad_output = _x(
        "move", "--to", "failed", "--observed", "x", "--failure-type", "flaky"
    )

    assert unclassified.exit_code == 1
    assert "needs a failure_type" in output
    assert classified.exit_code == 0
    assert bad.exit_code == 1


def test_preconditions_are_recorded() -> None:
    result, output = _x(
        "preconditions", "--met", "App is up", "--unmet", "Test user exists"
    )

    assert result.exit_code == 0
    assert "2 preconditions recorded." in output


def test_interrupted_runs_are_found_and_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _x("step-start", "--number", "1", "--action", "Submit")
    quiet, quiet_output = _run("executions", "interrupted", "-p", "PROJ-001")
    later = datetime.now().astimezone() + timedelta(hours=2)
    monkeypatch.setattr("qa_workbench.executions.recovery._now", lambda: later)

    found, found_output = _run("executions", "interrupted", "-p", "PROJ-001")
    recovered, recovered_output = _x(
        "recover", "--action", "resume", "--note", "Laptop slept"
    )

    assert quiet.exit_code == 0
    assert "No interrupted executions." in quiet_output
    assert found.exit_code == 0
    assert "EXEC-001" in found_output and "step 1 was in progress" in found_output
    assert recovered.exit_code == 0
    assert "EXEC-001 is now running." in recovered_output


def test_an_execution_can_be_abandoned_and_nothing_is_invented() -> None:
    _x("step-start", "--number", "1", "--action", "Submit")

    result, output = _x("recover", "--action", "abandon", "--note", "Power cut")
    _, body = _x("show")

    assert result.exit_code == 0
    assert "EXEC-001 is now inconclusive." in output
    assert "1. Submit - interrupted" in body
    assert "Interrupted and abandoned: Power cut" in body


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--action", "ignore", "--note", "x"], "action must be resume or abandon"),
        (["--action", "resume", "--note", " "], "needs a note"),
    ],
)
def test_recovery_input_is_validated(args: list[str], message: str) -> None:
    result, output = _x("recover", *args)

    assert result.exit_code == 1
    assert message in output


def test_rerun_and_corrections_never_touch_the_original() -> None:
    _x("move", "--to", "blocked", "--reason", "Staging was down")
    _x("move", "--to", "finalized")

    rerun, rerun_output = _x("rerun")
    corrected, corrected_output = _x(
        "correct", "--author", "Ana", "--justification", "Wrong environment"
    )
    added, _ = _x(
        "correct",
        "--author",
        "Bruno",
        "--justification",
        "Linked the ticket",
        "--addition",
    )
    history, history_output = _x("history")

    assert rerun.exit_code == 0
    assert "Created EXEC-002 (rerun of EXEC-001)." in rerun_output
    assert corrected.exit_code == 0
    assert "correction #2 recorded." in corrected_output
    assert added.exit_code == 0
    assert history.exit_code == 0
    assert "sealed  qa-workbench" in history_output
    assert "correction  Ana: Wrong environment" in history_output
    assert "addition  Bruno: Linked the ticket" in history_output


def test_a_running_execution_cannot_be_rerun_or_corrected() -> None:
    rerun, rerun_output = _x("rerun")
    corrected, corrected_output = _x(
        "correct", "--author", "Ana", "--justification", "x"
    )

    assert rerun.exit_code == 1
    assert "only an execution with a result can be rerun" in rerun_output
    assert corrected.exit_code == 1
    assert "is not finalized" in corrected_output


def test_history_reports_tampering(isolated_data: Path) -> None:
    _x("move", "--to", "blocked", "--reason", "Down")
    _x("move", "--to", "finalized")
    path = isolated_data / "projects" / "PROJ-001" / "executions" / "EXEC-001.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("reason: Down", "reason: Edited"),
        encoding="utf-8",
    )

    result, output = _x("history")

    assert result.exit_code == 1
    assert "modified after it was finalized" in output


def test_history_of_an_unfinalized_execution_says_so() -> None:
    result, output = _x("history")

    assert result.exit_code == 0
    assert "No history: the execution is not finalized." in output
