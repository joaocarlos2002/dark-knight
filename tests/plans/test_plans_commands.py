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
def project(isolated_data: Path, tmp_path: Path) -> None:
    assert _run("project", "create", "Demo")[0].exit_code == 0
    source = tmp_path / "reqs.md"
    source.write_text("## Users can log in\n\n## Users can log out\n", encoding="utf-8")
    assert (
        _run("requirements", "import", str(source), "-p", "PROJ-001")[0].exit_code == 0
    )


def _plan(*extra: str):
    return _run(
        "plans",
        "create",
        "Release 1.4",
        "-p",
        "PROJ-001",
        "--scope",
        "Checkout",
        "--strategy",
        "Risk based",
        "--objective",
        "No regressions",
        "--entry-criterion",
        "Build ready",
        "--exit-criterion",
        "No critical bugs",
        *extra,
    )


def _active_case(requirement: str = "REQ-001") -> None:
    _run(
        "cases",
        "create",
        "Log in",
        "-p",
        "PROJ-001",
        "--objective",
        "Validate",
        "--step",
        "Open the page",
        "--expected-result",
        "Done",
        "--requirement",
        requirement,
    )
    case_id = "TC-001"
    assert _run("review", "submit", case_id, "-p", "PROJ-001")[0].exit_code == 0
    done, _ = _run(
        "review",
        "decide",
        case_id,
        "-p",
        "PROJ-001",
        "--decision",
        "approved",
        "--reviewer",
        "Ana",
    )
    assert done.exit_code == 0


def test_create_list_and_show() -> None:
    created, output = _plan("--owner", "Ana", "--environment", "staging")

    listed, listing = _run("plans", "list", "-p", "PROJ-001")
    shown, body = _run("plans", "show", "TP-001", "-p", "PROJ-001")

    assert created.exit_code == 0
    assert "Created TP-001  Release 1.4" in output
    assert "TP-001  draft        Release 1.4" in listing
    assert shown.exit_code == 0
    assert "## Exit criteria" in body
    assert "- No critical bugs" in body
    assert "## Owners\n\n- Ana" in body


def test_a_plan_needs_its_required_lists() -> None:
    result, output = _run(
        "plans",
        "create",
        "Thin",
        "-p",
        "PROJ-001",
        "--scope",
        "s",
        "--strategy",
        "s",
    )

    assert result.exit_code == 1
    assert "objectives needs at least one item." in output
    assert "exit_criteria needs at least one item." in output


def test_list_without_plans_explains_how_to_start() -> None:
    result, output = _run("plans", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "No test plans yet" in output


def test_recommend_explains_every_decision() -> None:
    _active_case()
    _run(
        "cases",
        "create",
        "Other",
        "-p",
        "PROJ-001",
        "--objective",
        "x",
        "--step",
        "y",
        "--expected-result",
        "z",
        "--requirement",
        "REQ-002",
    )

    result, output = _run(
        "plans", "recommend", "-p", "PROJ-001", "--requirement", "REQ-001"
    )

    assert result.exit_code == 0
    assert "INCLUDE TC-001" in output
    assert "changed_requirements: covers changed REQ-001" in output
    assert "coverage: the only active case covering REQ-001" in output
    assert "EXCLUDE TC-002" in output
    assert "readiness: the case is draft, not active" in output
    assert "1 of 2 cases included." in output
    assert "Not considered - defect_history" in output


def test_recommend_can_store_the_selection_on_a_plan() -> None:
    _plan()
    _active_case()

    result, output = _run(
        "plans",
        "recommend",
        "-p",
        "PROJ-001",
        "--requirement",
        "REQ-001",
        "--save-to",
        "TP-001",
    )
    _, body = _run("plans", "show", "TP-001", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "Selection stored on TP-001" in output
    assert "### Include TC-001" in body
    assert "- changed_requirements: covers changed REQ-001" in body


def test_verify_accepts_a_sound_selection_and_rejects_a_broken_one(
    isolated_data: Path,
) -> None:
    _plan()
    _active_case()
    _run(
        "plans",
        "recommend",
        "-p",
        "PROJ-001",
        "--requirement",
        "REQ-001",
        "--save-to",
        "TP-001",
    )

    good, good_output = _run("plans", "verify", "TP-001", "-p", "PROJ-001")
    (isolated_data / "projects" / "PROJ-001" / "test-cases" / "TC-001.md").unlink()
    bad, bad_output = _run("plans", "verify", "TP-001", "-p", "PROJ-001")

    assert good.exit_code == 0
    assert "TP-001: the selection is sound." in good_output
    assert bad.exit_code == 1
    assert "Missing: TC-001 does not exist." in bad_output


def test_a_time_budget_is_applied() -> None:
    _active_case()

    result, output = _run(
        "plans",
        "recommend",
        "-p",
        "PROJ-001",
        "--requirement",
        "REQ-001",
        "--budget",
        "30",
    )

    assert result.exit_code == 0
    assert "time: no estimate, so it is not counted against the budget" in output
    assert "0 min estimated." in output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--requirement", "REQ-099"], "Unknown changed requirement"),
        (["--budget", "0"], "at least 1 minute"),
    ],
)
def test_invalid_recommendation_input_is_refused(args: list[str], message: str) -> None:
    result, output = _run("plans", "recommend", "-p", "PROJ-001", *args)

    assert result.exit_code == 1
    assert message in output


def test_an_unknown_plan_is_reported() -> None:
    result, output = _run("plans", "show", "TP-404", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "TP-404 was not found" in output


def test_an_archived_project_cannot_receive_plans() -> None:
    _run("project", "archive", "PROJ-001")

    result, output = _plan()

    assert result.exit_code == 1
    assert "PROJ-001 is archived and cannot be changed" in output
