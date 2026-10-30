from pathlib import Path
from typing import Any

import pytest

from qa_workbench.executions.schema import EXECUTION_SCHEMA, EXECUTION_TYPES
from qa_workbench.executions.service import (
    ExecutionError,
    create_execution,
    move,
    render_body,
)
from qa_workbench.executions.states import InvalidTransition
from qa_workbench.storage.errors import RecordFinalizedError, RecordValidationError
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(
        tmp_path / "project", [EXECUTION_SCHEMA, TEST_CASE_SCHEMA, EVIDENCE_SCHEMA]
    )


@pytest.fixture
def case(repo: MarkdownRepository):
    draft = TestCaseDraft(
        title="Log in",
        objective="Validate login",
        steps=[Step("Submit credentials")],
        expected_result="The user is authenticated",
    )
    return create_test_case(repo, draft, status="active")


@pytest.fixture
def evidence(repo: MarkdownRepository, tmp_path: Path):
    file = tmp_path / "shot.png"
    file.write_bytes(b"png")
    return EvidenceStore(repo).register(file, source="manual", description="Login")


def _create(repo: MarkdownRepository, **overrides: Any):
    values: dict[str, Any] = {
        "execution_type": "manual",
        "executor": "Ana",
        "environment": "staging",
        "test_case": "TC-001",
    }
    values.update(overrides)
    return create_execution(repo, **values)


def _run_to(repo: MarkdownRepository, execution_id: str, *states: str, **data: Any):
    record = None
    for state in states:
        record = move(
            repo,
            execution_id,
            state,
            **data if state in data.get("_on", states[-1:]) else {},
        )
    return record


# --- creation -----------------------------------------------------------------


def test_an_execution_starts_in_created_with_what_was_expected(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo, version="1.4.0", branch="develop", commit="abc123")

    metadata = record.metadata
    assert record.id == "EXEC-001"
    assert metadata["status"] == "created"
    assert metadata["execution_type"] == "manual"
    assert metadata["executor"] == "Ana"
    assert metadata["expected_result"] == "The user is authenticated"
    assert (metadata["version"], metadata["branch"], metadata["commit"]) == (
        "1.4.0",
        "develop",
        "abc123",
    )
    assert "result" not in metadata
    assert "started_at" not in metadata


@pytest.mark.parametrize(
    "kind", sorted(EXECUTION_TYPES - {"agent_driven", "automated"})
)
def test_human_and_exploratory_types_are_accepted(
    repo: MarkdownRepository, case, kind: str
) -> None:
    assert _create(repo, execution_type=kind).metadata["execution_type"] == kind


@pytest.mark.parametrize("kind", ["agent_driven", "automated"])
def test_machine_types_need_an_automation_tool(
    repo: MarkdownRepository, case, kind: str
) -> None:
    with pytest.raises(RecordValidationError, match="needs automation_tool"):
        _create(repo, execution_type=kind)

    record = _create(repo, execution_type=kind, automation_tool="playwright")
    assert record.metadata["automation_tool"] == "playwright"


@pytest.mark.parametrize("kind", ["manual", "assisted_manual"])
def test_agent_automation_cannot_be_recorded_as_a_human_execution(
    repo: MarkdownRepository, case, kind: str
) -> None:
    with pytest.raises(RecordValidationError, match="cannot name an automation tool"):
        _create(repo, execution_type=kind, automation_tool="playwright")


def test_an_unknown_type_is_refused(repo: MarkdownRepository, case) -> None:
    with pytest.raises(RecordValidationError, match="execution_type 'robot'"):
        _create(repo, execution_type="robot")


def test_the_test_case_must_exist_and_be_active(repo: MarkdownRepository, case) -> None:
    draft = TestCaseDraft(
        title="Draft",
        objective="x",
        steps=[Step("s")],
        expected_result="e",
    )
    create_test_case(repo, draft)

    with pytest.raises(ExecutionError, match="TC-099 does not exist"):
        _create(repo, test_case="TC-099")
    with pytest.raises(ExecutionError, match="TC-002 is draft"):
        _create(repo, test_case="TC-002")
    assert repo.record_ids("EXEC") == []


def test_an_exploratory_session_needs_no_test_case(repo: MarkdownRepository) -> None:
    record = _create(repo, execution_type="exploratory", test_case=None)

    assert "test_case" not in record.metadata


def test_other_types_need_a_test_case(repo: MarkdownRepository) -> None:
    with pytest.raises(RecordValidationError, match="test_case is required"):
        _create(repo, test_case=None)


def test_executor_and_environment_are_required(repo: MarkdownRepository, case) -> None:
    with pytest.raises(RecordValidationError) as error:
        _create(repo, executor=" ", environment="")

    assert "executor is required." in "\n".join(error.value.problems)
    assert "environment is required." in "\n".join(error.value.problems)


def test_the_body_follows_the_specification_headings(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo)

    assert record.body == (
        "# EXEC-001\n\n"
        "## Objective\n\nValidate TC-001.\n\n"
        "## Expected result\n\nThe user is authenticated\n\n"
        "## Observed result\n\n"
        "## Evidence\n\n"
        "## Notes\n\n"
        "## Conclusion\n"
    )


def test_render_body_copes_with_an_empty_record() -> None:
    assert render_body({}).startswith("# Execution\n")


# --- the lifecycle ------------------------------------------------------------


def test_the_full_lifecycle_to_a_sealed_pass(
    repo: MarkdownRepository, case, evidence
) -> None:
    record = _create(repo)
    move(repo, record.id, "planned")
    running = move(repo, record.id, "running")
    passed = move(
        repo,
        record.id,
        "passed",
        observed_result="The user reached the dashboard.",
        evidence=[evidence.id],
    )
    final = move(repo, record.id, "finalized")

    assert running.metadata["started_at"].utcoffset() is not None
    assert passed.metadata["result"] == "passed"
    assert passed.metadata["finished_at"] >= passed.metadata["started_at"]
    assert passed.metadata["duration_seconds"] >= 0
    assert final.metadata["status"] == "finalized"
    assert final.metadata["result"] == "passed"
    assert [e.kind for e in repo.history(record.id)] == ["sealed"]
    assert repo.verify(record.id) == []


def test_a_finalized_execution_can_neither_move_nor_be_edited(
    repo: MarkdownRepository, case, evidence
) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")
    move(repo, record.id, "passed", observed_result="ok", evidence=[evidence.id])
    move(repo, record.id, "finalized")

    with pytest.raises(InvalidTransition, match="finalized is final"):
        move(repo, record.id, "running")
    with pytest.raises(RecordFinalizedError):
        repo.update(record.id, {"notes": "rewrite"})


@pytest.mark.parametrize(
    ("source_path", "target", "message"),
    [
        ([], "running", "Cannot move from created to running"),
        (["planned"], "passed", "Cannot move from planned to passed"),
        (["planned", "running"], "finalized", "Cannot move from running to finalized"),
        (["planned"], "created", "Cannot move from planned to created"),
    ],
)
def test_invalid_transitions_are_refused_and_nothing_changes(
    repo: MarkdownRepository,
    case,
    source_path: list[str],
    target: str,
    message: str,
) -> None:
    record = _create(repo)
    for state in source_path:
        move(repo, record.id, state)
    before = record.path.read_text(encoding="utf-8")

    with pytest.raises(InvalidTransition, match=message):
        move(repo, record.id, target)

    assert record.path.read_text(encoding="utf-8") == before


def test_unknown_target_states_are_refused(repo: MarkdownRepository, case) -> None:
    record = _create(repo)

    with pytest.raises(ValueError, match="Unknown state 'done'"):
        move(repo, record.id, "done")


def test_a_pass_needs_evidence_and_an_observed_result(
    repo: MarkdownRepository, case, evidence
) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")

    with pytest.raises(RecordValidationError) as error:
        move(repo, record.id, "passed")

    problems = "\n".join(error.value.problems)
    assert "a passed execution needs evidence." in problems
    assert "a passed execution needs the observed result." in problems
    assert repo.get(record.id).metadata["status"] == "running"


def test_evidence_that_does_not_exist_is_never_accepted(
    repo: MarkdownRepository, case, evidence
) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")

    with pytest.raises(ExecutionError, match="does not exist: EVD-099"):
        move(repo, record.id, "passed", observed_result="ok", evidence=["EVD-099"])

    assert repo.get(record.id).metadata["status"] == "running"


def test_a_failure_needs_the_observed_result(repo: MarkdownRepository, case) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")

    with pytest.raises(RecordValidationError, match="a failed execution needs"):
        move(repo, record.id, "failed")

    failed = move(
        repo, record.id, "failed", observed_result="Error 500", bugs=["BUG-001"]
    )
    assert failed.metadata["result"] == "failed"
    assert failed.metadata["bugs"] == ["BUG-001"]


@pytest.mark.parametrize("result", ["blocked", "inconclusive"])
def test_blocked_and_inconclusive_need_a_reason_and_never_become_a_pass(
    repo: MarkdownRepository, case, result: str
) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")

    with pytest.raises(
        RecordValidationError, match=f"a {result} execution needs a reason"
    ):
        move(repo, record.id, result)
    moved = move(repo, record.id, result, reason="Environment was down")

    assert moved.metadata["reason"] == "Environment was down"
    with pytest.raises(InvalidTransition):
        move(repo, record.id, "passed")
    assert "Environment was down" in moved.body


def test_an_execution_can_be_cancelled_before_it_starts(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo)

    cancelled = move(repo, record.id, "cancelled", reason="Superseded by a new build")
    final = move(repo, record.id, "finalized")

    assert "started_at" not in cancelled.metadata
    assert cancelled.metadata["finished_at"].utcoffset() is not None
    assert "duration_seconds" not in cancelled.metadata
    assert final.metadata["result"] == "cancelled"


def test_cancelling_needs_a_reason(repo: MarkdownRepository, case) -> None:
    record = _create(repo)

    with pytest.raises(
        RecordValidationError, match="a cancelled execution needs a reason"
    ):
        move(repo, record.id, "cancelled")


# --- approval -----------------------------------------------------------------


def test_an_execution_that_needs_approval_cannot_run_without_it(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo, requires_approval=True)
    move(repo, record.id, "planned")

    with pytest.raises(InvalidTransition, match="requires approval"):
        move(repo, record.id, "running")


def test_approval_is_recorded_with_who_and_when(repo: MarkdownRepository, case) -> None:
    record = _create(repo, requires_approval=True)
    _run_to(repo, record.id, "planned", "awaiting_approval")

    running = move(repo, record.id, "running", approved_by="Bruno")

    assert running.metadata["approved_by"] == "Bruno"
    assert running.metadata["approved_at"].utcoffset() is not None


def test_approval_needs_a_name(repo: MarkdownRepository, case) -> None:
    record = _create(repo, requires_approval=True)
    _run_to(repo, record.id, "planned", "awaiting_approval")

    with pytest.raises(ExecutionError, match="needs approved_by"):
        move(repo, record.id, "running")
    with pytest.raises(ExecutionError, match="needs approved_by"):
        move(repo, record.id, "running", approved_by="  ")


def test_an_agent_cannot_approve_its_own_run(repo: MarkdownRepository, case) -> None:
    record = _create(
        repo,
        execution_type="agent_driven",
        executor="alfred",
        automation_tool="playwright",
        requires_approval=True,
    )
    _run_to(repo, record.id, "planned", "awaiting_approval")

    with pytest.raises(ExecutionError, match="different from the executor"):
        move(repo, record.id, "running", approved_by="Alfred")


def test_an_awaiting_execution_can_be_cancelled_instead(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo, requires_approval=True)
    _run_to(repo, record.id, "planned", "awaiting_approval")

    moved = move(repo, record.id, "cancelled", reason="Approval denied")

    assert moved.metadata["status"] == "cancelled"


# --- hand-edited records ------------------------------------------------------


def _edit(record, old: str, new: str) -> None:
    record.path.write_text(
        record.path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8"
    )


def test_a_hand_edited_pass_without_evidence_is_rejected_when_read(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo)

    _edit(record, "status: created", "status: passed\nresult: passed")

    with pytest.raises(
        RecordValidationError, match="a passed execution needs evidence"
    ):
        repo.get(record.id)


def test_a_result_before_the_execution_finishes_is_rejected(
    repo: MarkdownRepository, case
) -> None:
    record = _create(repo)

    _edit(record, "status: created", "status: created\nresult: passed")

    with pytest.raises(RecordValidationError, match="has no result yet"):
        repo.get(record.id)


def test_finishing_before_starting_is_rejected(repo: MarkdownRepository, case) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")
    failed = move(repo, record.id, "failed", observed_result="x")
    text = failed.path.read_text(encoding="utf-8")
    start = next(line for line in text.splitlines() if line.startswith("started_at:"))
    failed.path.write_text(
        text.replace(start, "started_at: 2099-01-01T00:00:00+00:00"), encoding="utf-8"
    )

    with pytest.raises(RecordValidationError, match="finished_at cannot be earlier"):
        repo.get(record.id)


def test_a_finalized_execution_edited_by_hand_is_detected(
    repo: MarkdownRepository, case, evidence
) -> None:
    record = _create(repo)
    _run_to(repo, record.id, "planned", "running")
    move(repo, record.id, "passed", observed_result="ok", evidence=[evidence.id])
    final = move(repo, record.id, "finalized")

    _edit(final, "observed_result: ok", "observed_result: edited")

    assert any("modified after it was finalized" in p for p in repo.verify(record.id))
