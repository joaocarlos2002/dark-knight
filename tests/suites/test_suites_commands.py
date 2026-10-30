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
    for title in ("Log in", "Log out"):
        result, _ = _run(
            "cases",
            "create",
            title,
            "-p",
            "PROJ-001",
            "--objective",
            "x",
            "--step",
            "s",
            "--expected-result",
            "ok",
        )
        assert result.exit_code == 0


def test_create_list_and_show() -> None:
    created, output = _run(
        "suites",
        "create",
        "Smoke",
        "-p",
        "PROJ-001",
        "--type",
        "smoke",
        "--case",
        "TC-001",
    )
    listed, listing = _run("suites", "list", "-p", "PROJ-001")
    shown, body = _run("suites", "show", "SUITE-001", "-p", "PROJ-001")

    assert created.exit_code == 0
    assert "Created SUITE-001  Smoke" in output
    assert "SUITE-001  draft     smoke            1 cases  Smoke" in listing
    assert shown.exit_code == 0
    assert "- [[TC-001]] Log in" in body


def test_a_case_belongs_to_several_suites() -> None:
    _run("suites", "create", "Smoke", "-p", "PROJ-001", "--type", "smoke")
    _run("suites", "create", "Regression", "-p", "PROJ-001", "--type", "regression")
    _run("suites", "add", "SUITE-001", "-p", "PROJ-001", "--case", "TC-001")
    added, output = _run(
        "suites",
        "add",
        "SUITE-002",
        "-p",
        "PROJ-001",
        "--case",
        "TC-001",
        "--case",
        "TC-002",
    )

    result, members = _run("suites", "membership", "-p", "PROJ-001")

    assert added.exit_code == 0
    assert "SUITE-002 now has 2 cases." in output
    assert result.exit_code == 0
    assert "TC-001  SUITE-001, SUITE-002" in members
    assert "TC-002  SUITE-002" in members


def test_remove_keeps_the_case_itself() -> None:
    _run(
        "suites",
        "create",
        "S",
        "-p",
        "PROJ-001",
        "--case",
        "TC-001",
        "--case",
        "TC-002",
    )

    removed, output = _run(
        "suites", "remove", "SUITE-001", "-p", "PROJ-001", "--case", "TC-001"
    )
    cases, listing = _run("cases", "list", "-p", "PROJ-001")

    assert removed.exit_code == 0
    assert "SUITE-001 now has 1 cases." in output
    assert "TC-001" in listing


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["add", "SUITE-001", "--case", "TC-001"], "already contains: TC-001"),
        (["add", "SUITE-001", "--case", "TC-099"], "do not exist: TC-099"),
        (["remove", "SUITE-001", "--case", "TC-002"], "does not contain: TC-002"),
        (["show", "SUITE-404"], "SUITE-404 was not found"),
    ],
)
def test_membership_mistakes_are_explained(args: list[str], message: str) -> None:
    _run("suites", "create", "S", "-p", "PROJ-001", "--case", "TC-001")

    result, output = _run("suites", *args, "-p", "PROJ-001")

    assert result.exit_code == 1
    assert message in output


def test_an_unknown_case_or_type_is_refused_on_create() -> None:
    bad_case, case_output = _run(
        "suites", "create", "S", "-p", "PROJ-001", "--case", "TC-099"
    )
    bad_type, type_output = _run(
        "suites", "create", "S", "-p", "PROJ-001", "--type", "magic"
    )

    assert bad_case.exit_code == 1
    assert "do not exist: TC-099" in case_output
    assert bad_type.exit_code == 1
    assert "type 'magic' is not allowed" in type_output


def test_verify_reports_missing_cases(isolated_data: Path) -> None:
    _run("suites", "create", "S", "-p", "PROJ-001", "--case", "TC-001")
    (isolated_data / "projects" / "PROJ-001" / "test-cases" / "TC-001.md").unlink()

    result, output = _run("suites", "verify", "SUITE-001", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "Missing: TC-001 does not exist." in output


def test_empty_projects_say_how_to_start() -> None:
    _, listing = _run("suites", "list", "-p", "PROJ-001")
    _, members = _run("suites", "membership", "-p", "PROJ-001")

    assert "No suites yet" in listing
    assert "No test case belongs to a suite yet." in members


def _plan_with_suite(suite_id: str):
    return _run(
        "plans",
        "create",
        "Plan",
        "-p",
        "PROJ-001",
        "--scope",
        "s",
        "--strategy",
        "s",
        "--objective",
        "o",
        "--entry-criterion",
        "e",
        "--exit-criterion",
        "x",
        "--suite",
        suite_id,
    )


def test_plan_verification_checks_the_suites_it_references() -> None:
    _run("suites", "create", "S", "-p", "PROJ-001", "--case", "TC-001")
    _plan_with_suite("SUITE-001")
    _plan_with_suite("SUITE-099")

    good, good_output = _run("plans", "verify", "TP-001", "-p", "PROJ-001")
    bad, bad_output = _run("plans", "verify", "TP-002", "-p", "PROJ-001")

    assert good.exit_code == 0
    assert "TP-001: the selection is sound." in good_output
    assert bad.exit_code == 1
    assert "Missing: SUITE-099 does not exist." in bad_output


def test_an_archived_project_cannot_receive_suites() -> None:
    _run("project", "archive", "PROJ-001")

    result, output = _run("suites", "create", "S", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "PROJ-001 is archived and cannot be changed" in output
