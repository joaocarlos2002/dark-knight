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
def finished_project(isolated_data: Path, tmp_path: Path) -> None:
    source = tmp_path / "reqs.md"
    source.write_text("## Users can log in\n\n## Users can log out\n", encoding="utf-8")
    proof = tmp_path / "proof.txt"
    proof.write_text("proof", encoding="utf-8")
    commands = [
        ["project", "create", "Demo"],
        ["requirements", "import", str(source), "-p", "PROJ-001"],
        [
            "cases",
            "create",
            "Log in",
            "-p",
            "PROJ-001",
            "--objective",
            "Validate login",
            "--step",
            "Open",
            "--expected-result",
            "ok",
            "--requirement",
            "REQ-001",
        ],
        ["review", "submit", "TC-001", "-p", "PROJ-001"],
        [
            "review",
            "decide",
            "TC-001",
            "-p",
            "PROJ-001",
            "--decision",
            "approved",
            "--reviewer",
            "Ana",
        ],
        [
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
        ],
        ["executions", "move", "EXEC-001", "-p", "PROJ-001", "--to", "planned"],
        ["executions", "move", "EXEC-001", "-p", "PROJ-001", "--to", "running"],
        [
            "evidence",
            "add",
            str(proof),
            "-p",
            "PROJ-001",
            "--source",
            "manual",
            "--description",
            "Dashboard",
        ],
        [
            "executions",
            "move",
            "EXEC-001",
            "-p",
            "PROJ-001",
            "--to",
            "passed",
            "--observed",
            "Dashboard shown",
            "--evidence",
            "EVD-001",
        ],
        ["executions", "move", "EXEC-001", "-p", "PROJ-001", "--to", "finalized"],
    ]
    for command in commands:
        result, output = _run(*command)
        assert result.exit_code == 0, output


def test_the_execution_report_is_printed() -> None:
    result, output = _run("reports", "execution", "EXEC-001", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "# Execution report EXEC-001" in output
    assert "✓ PASSED" in output
    assert "- [[EVD-001]] Dashboard" in output
    assert "- The steps were not recorded one by one." in output


def test_the_execution_report_can_be_saved(isolated_data: Path) -> None:
    result, output = _run(
        "reports", "execution", "EXEC-001", "-p", "PROJ-001", "--save"
    )

    saved = isolated_data / "projects" / "PROJ-001" / "reports" / "EXEC-001.md"
    assert result.exit_code == 0
    assert "Saved" in output
    assert saved.is_file()
    assert "source_sha256:" in saved.read_text(encoding="utf-8")


def test_a_stale_saved_report_is_flagged() -> None:
    _run("reports", "execution", "EXEC-001", "-p", "PROJ-001", "--save")
    _run(
        "executions",
        "correct",
        "EXEC-001",
        "-p",
        "PROJ-001",
        "--author",
        "Ana",
        "--justification",
        "Wrong version",
    )

    result, output = _run("reports", "execution", "EXEC-001", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "Correction recorded by Ana: Wrong version" in output
    assert "the saved report is out of date" in output


def test_the_traceability_matrix_is_printed_and_saved(isolated_data: Path) -> None:
    printed, output = _run("reports", "traceability", "-p", "PROJ-001")
    saved, saved_output = _run("reports", "traceability", "-p", "PROJ-001", "--save")

    assert printed.exit_code == 0
    assert "| [[REQ-001]] | Users can log in | [[TC-001]] EXEC-001: passed" in output
    assert "- [[REQ-002]] has no test case." in output
    assert saved.exit_code == 0
    assert "Saved" in saved_output
    assert (
        isolated_data / "projects" / "PROJ-001" / "reports" / "traceability.md"
    ).is_file()


def test_trace_follows_the_chain_both_ways() -> None:
    down, down_output = _run("reports", "trace", "REQ-001", "-p", "PROJ-001")
    up, up_output = _run("reports", "trace", "EXEC-001", "-p", "PROJ-001")

    assert down.exit_code == 0
    assert "Downstream TC: TC-001" in down_output
    assert "Downstream EXEC: EXEC-001" in down_output
    assert "Downstream EVD: EVD-001" in down_output
    assert up.exit_code == 0
    assert "Upstream REQ: REQ-001" in up_output
    assert "Upstream TC: TC-001" in up_output


def test_an_unlinked_record_says_so() -> None:
    result, output = _run("reports", "trace", "REQ-002", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "REQ-002 is not linked to any other record." in output


def test_unknown_and_malformed_ids_are_refused() -> None:
    unknown, unknown_output = _run("reports", "trace", "REQ-404", "-p", "PROJ-001")
    malformed, _ = _run("reports", "trace", "nope", "-p", "PROJ-001")
    missing, missing_output = _run("reports", "execution", "EXEC-404", "-p", "PROJ-001")

    assert unknown.exit_code == 1
    assert "REQ-404 was not found." in unknown_output
    assert malformed.exit_code == 1
    assert missing.exit_code == 1
    assert "EXEC-404 was not found" in missing_output


def test_an_archived_project_can_be_reported_on_but_not_saved_to() -> None:
    _run("project", "archive", "PROJ-001")

    printed, _ = _run("reports", "execution", "EXEC-001", "-p", "PROJ-001")
    saved, saved_output = _run(
        "reports", "execution", "EXEC-001", "-p", "PROJ-001", "--save"
    )

    assert printed.exit_code == 0
    assert saved.exit_code == 1
    assert "archived and cannot be changed" in saved_output
