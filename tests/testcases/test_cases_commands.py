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
    result, _ = _run("project", "create", "Demo")
    assert result.exit_code == 0


def _create(*extra: str):
    return _run(
        "cases",
        "create",
        "Log in",
        "-p",
        "PROJ-001",
        "--objective",
        "Validate login",
        "--step",
        "Open the page",
        "--step",
        "Submit => Dashboard is shown",
        "--expected-result",
        "The user is authenticated",
        *extra,
    )


def test_create_writes_a_draft_case(isolated_data: Path) -> None:
    result, output = _create("--requirement", "REQ-001", "--tag", "auth")

    assert result.exit_code == 0
    assert "Created TC-001  Log in" in output
    path = isolated_data / "projects" / "PROJ-001" / "test-cases" / "TC-001.md"
    text = path.read_text(encoding="utf-8")
    assert "status: draft" in text
    assert "requirements: [REQ-001]" in text
    assert "expected: Dashboard is shown" in text


def test_list_and_show(isolated_data: Path) -> None:
    _create()

    listed, listing = _run("cases", "list", "-p", "PROJ-001")
    shown, body = _run("cases", "show", "TC-001", "-p", "PROJ-001")

    assert listed.exit_code == 0
    assert "TC-001  draft       medium  functional    Log in" in listing
    assert shown.exit_code == 0
    assert "## Steps" in body
    assert "   - Expected: Dashboard is shown" in body


def test_list_without_cases_explains_how_to_start() -> None:
    result, output = _run("cases", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "No test cases yet" in output


def test_invalid_input_lists_every_problem_and_exits_with_one() -> None:
    result, output = _run(
        "cases",
        "create",
        "Bad",
        "-p",
        "PROJ-001",
        "--objective",
        "x",
        "--priority",
        "urgent",
        "--step",
        "password=hunter2",
    )

    assert result.exit_code == 1
    assert "priority 'urgent' is not allowed" in output
    assert "step 1 action contains a literal password value" in output
    assert "expected_result is required" in output


def test_an_unknown_case_is_reported() -> None:
    result, output = _run("cases", "show", "TC-404", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "TC-404 was not found" in output


def test_a_case_makes_its_requirement_covered(tmp_path: Path) -> None:
    source = tmp_path / "reqs.md"
    source.write_text("## Users can log in\n", encoding="utf-8")
    _run("requirements", "import", str(source), "-p", "PROJ-001")
    _create("--requirement", "REQ-001")

    result, output = _run("requirements", "coverage", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "REQ-001  covered    Users can log in  [TC-001]" in output
    assert "1 of 1 requirements covered." in output


def test_an_archived_project_cannot_receive_cases() -> None:
    _run("project", "archive", "PROJ-001")

    result, output = _create()

    assert result.exit_code == 1
    assert "PROJ-001 is archived and cannot be changed" in output
