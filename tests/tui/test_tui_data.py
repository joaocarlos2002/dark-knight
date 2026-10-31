from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qa_workbench.executions.recording import finish_step, start_step
from qa_workbench.executions.service import create_execution, move
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.tui.data import (
    build_overview,
    duration_text,
    effective_status,
    project_rows,
)
from qa_workbench.tui.status import Status
from qa_workbench.workspace import repository_for


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo", repository="https://g.test/a/b")


@pytest.fixture
def repo(tmp_path: Path, project):
    return repository_for(tmp_path, project)


def _case(repo, title="Log in"):
    draft = TestCaseDraft(
        title=title,
        objective="Validate that a user can sign in.",
        preconditions=["The app is up"],
        steps=[Step("Open the page")],
        expected_result="The dashboard is shown.",
    )
    return create_test_case(repo, draft, status="active")


def _png(root: Path) -> Path:
    path = root / f"shot-{len(list(root.glob('shot-*.png')))}.png"
    path.write_bytes(b"png")
    return path


def _execution(repo, case_id: str, outcome: str | None, finalize: bool = True):
    record = create_execution(
        repo,
        execution_type="manual",
        executor="Ana",
        environment="staging",
        test_case=case_id,
        version="1",
    )
    if outcome is None:
        return record
    move(repo, record.id, "planned")
    move(repo, record.id, "running")
    if outcome == "running":
        return record
    start_step(repo, record.id, 1, "Open the page")
    finish_step(
        repo,
        record.id,
        1,
        outcome,
        observed="seen",
        failure_type="product" if outcome == "failed" else None,
    )
    evidence = EvidenceStore(repo).register(
        _png(repo.root), source="manual", description="proof"
    )
    extra = {"observed_result": "seen", "evidence": [evidence.id]}
    if outcome == "failed":
        extra["failure_type"] = "product"
    move(repo, record.id, outcome, **extra)
    if finalize:
        move(repo, record.id, "finalized")
    return record


def test_project_rows_are_readable(tmp_path: Path, project) -> None:
    rows = project_rows(ProjectRepository(tmp_path).list_projects())

    assert [(r.id, r.name, r.status, r.repository) for r in rows] == [
        ("PROJ-001", "Demo", "active", "https://g.test/a/b")
    ]
    assert rows[0].environments == "-"


def test_an_empty_project_has_zero_records_not_unavailable(repo, project) -> None:
    data = build_overview(repo, project)

    assert data.test_cases == 0 and data.requirements == 0
    assert data.results["passed"] == 0 and data.recent == () and data.problems == ()


def test_counts_come_from_the_records(repo, project) -> None:
    case = _case(repo)
    _case(repo, "Log out")
    _execution(repo, case.id, "passed")
    _execution(repo, case.id, "passed", finalize=False)
    _execution(repo, case.id, "failed")
    _execution(repo, case.id, None)  # created, not run
    _execution(repo, case.id, "running")

    data = build_overview(repo, project)

    assert data.test_cases == 2
    assert data.results["passed"] == 2 and data.results["failed"] == 1
    assert data.results["blocked"] == 0
    assert data.in_progress == 2  # one created, one running


def test_recent_executions_are_newest_first_with_case_titles(repo, project) -> None:
    case = _case(repo, "Checkout works")
    first = _execution(repo, case.id, "passed")
    second = _execution(repo, case.id, "failed")

    data = build_overview(repo, project)

    assert [r.id for r in data.recent] == [second.id, first.id]
    assert data.recent[0].case == "TC-001 Checkout works"
    assert data.recent[0].status is Status.FAILED
    assert data.recent[1].status is Status.PASSED


def test_a_missing_case_is_said_not_hidden(repo, project) -> None:
    case = _case(repo)
    record = _execution(repo, case.id, None)
    repo.path_of(case.id).unlink()

    data = build_overview(repo, project)

    assert data.recent[0].id == record.id
    assert "record not found" in data.recent[0].case


def test_damaged_records_are_reported_and_not_counted(repo, project) -> None:
    case = _case(repo)
    _case(repo, "Other")
    repo.path_of("TC-002").write_text("not a record", encoding="utf-8")

    data = build_overview(repo, project)

    assert data.test_cases == 1 and case.id == "TC-001"
    assert len(data.problems) == 1 and data.problems[0].startswith("TC:")


def test_effective_status_and_duration() -> None:
    assert effective_status({"status": "finalized", "result": "failed"}) == "failed"
    assert effective_status({"status": "running"}) == "running"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert duration_text(start, start + timedelta(seconds=75)) == "01:15"
    assert duration_text(start, None) == "-"
    assert duration_text(None, None) == "-"
