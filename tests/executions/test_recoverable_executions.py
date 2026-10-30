from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from qa_workbench.executions.recording import (
    check_preconditions,
    finish_step,
    start_step,
)
from qa_workbench.executions.recovery import (
    ABANDON,
    RESUME,
    find_interrupted,
    record_correction,
    recover,
    rerun,
)
from qa_workbench.executions.schema import EXECUTION_SCHEMA
from qa_workbench.executions.service import ExecutionError, create_execution, move
from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(
        tmp_path / "project", [EXECUTION_SCHEMA, TEST_CASE_SCHEMA, EVIDENCE_SCHEMA]
    )


@pytest.fixture(autouse=True)
def case(repo: MarkdownRepository):
    draft = TestCaseDraft(
        title="Log in",
        objective="Validate login",
        steps=[Step("Submit credentials")],
        expected_result="Authenticated",
    )
    return create_test_case(repo, draft, status="active")


@pytest.fixture
def evidence(repo: MarkdownRepository, tmp_path: Path):
    file = tmp_path / "shot.png"
    file.write_bytes(b"png")
    return EvidenceStore(repo).register(file, source="manual", description="Login")


def _running(repo: MarkdownRepository, **overrides: Any):
    values: dict[str, Any] = {
        "execution_type": "manual",
        "executor": "Ana",
        "environment": "staging",
        "test_case": "TC-001",
    }
    values.update(overrides)
    record = create_execution(repo, **values)
    move(repo, record.id, "planned")
    return move(repo, record.id, "running")


# --- incremental recording ----------------------------------------------------


def test_a_step_is_saved_as_in_progress_before_it_is_carried_out(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)

    start_step(repo, record.id, 1, "Open the login page")

    # Read with a fresh repository, as a process that restarted would.
    fresh = MarkdownRepository(repo.root, repo.schemas)
    (step,) = fresh.get(record.id).metadata["steps_executed"]
    assert step["number"] == 1
    assert step["action"] == "Open the login page"
    assert step["started_at"].utcoffset() is not None
    assert "outcome" not in step


def test_finishing_a_step_records_what_was_observed(
    repo: MarkdownRepository, evidence
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Open the login page")

    done = finish_step(
        repo,
        record.id,
        1,
        "passed",
        observed="The form is shown",
        evidence=[evidence.id],
    )

    (step,) = done.metadata["steps_executed"]
    assert step["outcome"] == "passed"
    assert step["observed"] == "The form is shown"
    assert step["evidence"] == [evidence.id]
    assert step["finished_at"] >= step["started_at"]
    assert "1. Open the login page - passed: The form is shown" in done.body


def test_every_call_is_durable_and_the_record_stays_valid(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)

    for number, action in enumerate(["Open", "Type", "Submit"], start=1):
        start_step(repo, record.id, number, action)
        assert len(repo.get(record.id).metadata["steps_executed"]) == number
        finish_step(repo, record.id, number, "passed")

    assert [s["outcome"] for s in repo.get(record.id).metadata["steps_executed"]] == [
        "passed",
        "passed",
        "passed",
    ]


def test_steps_are_numbered_in_order(repo: MarkdownRepository) -> None:
    record = _running(repo)

    with pytest.raises(ExecutionError, match="next step is number 1, not 2"):
        start_step(repo, record.id, 2, "Skip ahead")
    start_step(repo, record.id, 1, "Open")
    finish_step(repo, record.id, 1, "passed")
    with pytest.raises(ExecutionError, match="next step is number 2, not 1"):
        start_step(repo, record.id, 1, "Again")


def test_a_new_step_cannot_start_while_one_is_in_progress(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Open")

    with pytest.raises(ExecutionError, match="Step 1 is still in progress"):
        start_step(repo, record.id, 2, "Next")


def test_only_the_step_in_progress_can_be_finished(repo: MarkdownRepository) -> None:
    record = _running(repo)

    with pytest.raises(ExecutionError, match="Step 1 is not the step in progress"):
        finish_step(repo, record.id, 1, "passed")
    start_step(repo, record.id, 1, "Open")
    finish_step(repo, record.id, 1, "passed")
    with pytest.raises(ExecutionError, match="Step 1 is not the step in progress"):
        finish_step(repo, record.id, 1, "failed")


@pytest.mark.parametrize("state", ["created", "planned"])
def test_steps_are_only_recorded_while_running(
    repo: MarkdownRepository, state: str
) -> None:
    record = create_execution(
        repo,
        execution_type="manual",
        executor="Ana",
        environment="staging",
        test_case="TC-001",
    )
    if state == "planned":
        move(repo, record.id, "planned")

    with pytest.raises(ExecutionError, match=f"is {state}; steps can only"):
        start_step(repo, record.id, 1, "Open")


def test_invalid_step_input_is_refused(repo: MarkdownRepository, evidence) -> None:
    record = _running(repo)

    with pytest.raises(ValueError, match="needs an action"):
        start_step(repo, record.id, 1, "  ")
    start_step(repo, record.id, 1, "Open")
    with pytest.raises(ValueError, match="outcome must be one of"):
        finish_step(repo, record.id, 1, "maybe")
    with pytest.raises(ValueError, match="failure_type must be one of"):
        finish_step(repo, record.id, 1, "failed", failure_type="bad")
    with pytest.raises(ExecutionError, match="does not exist: EVD-099"):
        finish_step(repo, record.id, 1, "passed", evidence=["EVD-099"])


def test_a_failed_step_needs_what_was_observed_and_a_failure_type(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Open")

    with pytest.raises(RecordValidationError) as error:
        finish_step(repo, record.id, 1, "failed")

    problems = "\n".join(error.value.problems)
    assert "failed step 1 needs the observed result" in problems
    assert "failed step 1 needs a failure_type" in problems
    assert "outcome" not in repo.get(record.id).metadata["steps_executed"][0]


def test_an_execution_cannot_pass_with_a_step_that_did_not(
    repo: MarkdownRepository, evidence
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Open")
    finish_step(repo, record.id, 1, "failed", observed="500", failure_type="product")

    with pytest.raises(RecordValidationError, match="steps that did not pass"):
        move(
            repo,
            record.id,
            "passed",
            observed_result="ok",
            evidence=[evidence.id],
        )


def test_skipped_steps_do_not_block_a_pass(repo: MarkdownRepository, evidence) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Optional banner")
    finish_step(repo, record.id, 1, "skipped", observed="Not shown in staging")

    passed = move(
        repo, record.id, "passed", observed_result="ok", evidence=[evidence.id]
    )

    assert passed.metadata["status"] == "passed"


def test_preconditions_are_recorded_with_their_result(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)

    updated = check_preconditions(
        repo,
        record.id,
        [("Application is available", True), ("Test user exists", False)],
    )

    assert updated.metadata["preconditions_checked"] == [
        {"text": "Application is available", "checked": True},
        {"text": "Test user exists", "checked": False},
    ]


def test_preconditions_cannot_be_recorded_after_the_execution_ends(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    move(repo, record.id, "blocked", reason="Environment down")

    with pytest.raises(ExecutionError, match="planned or running"):
        check_preconditions(repo, record.id, [("x", True)])


# --- failure classification ---------------------------------------------------


def _fail(repo: MarkdownRepository, record_id: str, **extra: Any):
    return move(repo, record_id, "failed", observed_result="Error 500", **extra)


def test_a_failure_must_be_classified(repo: MarkdownRepository) -> None:
    record = _running(repo)

    with pytest.raises(RecordValidationError, match="needs a failure_type"):
        _fail(repo, record.id)


@pytest.mark.parametrize(
    "kind", ["product", "test", "infrastructure", "evidence_collection"]
)
def test_the_four_kinds_of_failure_are_accepted(
    repo: MarkdownRepository, kind: str
) -> None:
    record = _running(repo)

    assert _fail(repo, record.id, failure_type=kind).metadata["failure_type"] == kind


def test_an_unknown_failure_kind_is_refused(repo: MarkdownRepository) -> None:
    record = _running(repo)

    with pytest.raises(
        RecordValidationError, match="failure_type 'flaky' is not allowed"
    ):
        _fail(repo, record.id, failure_type="flaky")


def test_defects_can_only_be_linked_to_product_failures(
    repo: MarkdownRepository,
) -> None:
    infra = _running(repo)
    product = _running(repo)

    with pytest.raises(
        RecordValidationError, match="only be linked to a product failure"
    ):
        _fail(repo, infra.id, failure_type="infrastructure", bugs=["BUG-001"])
    linked = _fail(repo, product.id, failure_type="product", bugs=["BUG-001"])

    assert linked.metadata["bugs"] == ["BUG-001"]


def test_a_blocked_run_can_say_why_it_was_infrastructure(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)

    blocked = move(
        repo,
        record.id,
        "blocked",
        reason="Staging was down",
        failure_type="infrastructure",
    )

    assert blocked.metadata["failure_type"] == "infrastructure"


def test_losing_the_evidence_is_not_a_pass(repo: MarkdownRepository) -> None:
    record = _running(repo)

    with pytest.raises(
        RecordValidationError, match="a passed execution needs evidence"
    ):
        move(repo, record.id, "passed", observed_result="Looked fine")
    inconclusive = move(
        repo,
        record.id,
        "inconclusive",
        reason="The screenshot could not be captured",
        failure_type="evidence_collection",
    )

    assert inconclusive.metadata["failure_type"] == "evidence_collection"


# --- recovery -----------------------------------------------------------------


def test_running_executions_without_recent_activity_are_found(
    repo: MarkdownRepository,
) -> None:
    stuck = _running(repo)
    start_step(repo, stuck.id, 1, "Open")
    finish_step(repo, stuck.id, 1, "passed")
    start_step(repo, stuck.id, 2, "Submit")
    _running(repo)
    later = repo.get(stuck.id).metadata["updated_at"] + timedelta(minutes=30)

    found = find_interrupted(repo, idle_for=timedelta(minutes=10), now=later)

    assert [(i.id, i.steps_done, i.step_in_progress) for i in found] == [
        (stuck.id, 1, 2),
        ("EXEC-002", 0, None),
    ]


def test_recent_and_not_running_executions_are_not_interrupted(
    repo: MarkdownRepository,
) -> None:
    running = _running(repo)
    planned = create_execution(
        repo,
        execution_type="manual",
        executor="Ana",
        environment="staging",
        test_case="TC-001",
    )
    move(repo, planned.id, "planned")
    soon = repo.get(running.id).metadata["updated_at"] + timedelta(minutes=5)

    assert find_interrupted(repo, idle_for=timedelta(minutes=10), now=soon) == []


def test_the_idle_threshold_must_be_positive(repo: MarkdownRepository) -> None:
    with pytest.raises(ValueError, match="longer than zero"):
        find_interrupted(repo, idle_for=timedelta(0))


def test_resuming_closes_the_unfinished_step_as_interrupted(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Submit")

    resumed = recover(repo, record.id, action=RESUME, note="Laptop went to sleep")

    (step,) = resumed.metadata["steps_executed"]
    assert step["outcome"] == "interrupted"
    assert "outcome was not observed" in step["observed"]
    (entry,) = resumed.metadata["recoveries"]
    assert (entry["action"], entry["note"], entry["interrupted_step"]) == (
        "resume",
        "Laptop went to sleep",
        1,
    )
    assert resumed.metadata["status"] == "running"
    start_step(repo, record.id, 2, "Submit again")
    assert len(repo.get(record.id).metadata["steps_executed"]) == 2


def test_abandoning_ends_it_as_inconclusive_and_keeps_the_finished_steps(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Open")
    finish_step(repo, record.id, 1, "passed")
    start_step(repo, record.id, 2, "Submit")

    abandoned = recover(repo, record.id, action=ABANDON, note="Power cut")

    assert abandoned.metadata["status"] == "inconclusive"
    assert abandoned.metadata["reason"] == "Interrupted and abandoned: Power cut"
    assert [s["outcome"] for s in abandoned.metadata["steps_executed"]] == [
        "passed",
        "interrupted",
    ]
    assert move(repo, record.id, "finalized").metadata["result"] == "inconclusive"


def test_recovery_never_invents_a_pass_or_a_failure(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Submit")

    abandoned = recover(repo, record.id, action=ABANDON, note="Crash")

    assert abandoned.metadata["status"] not in {"passed", "failed"}


def test_recovery_needs_a_note_and_a_valid_action(repo: MarkdownRepository) -> None:
    record = _running(repo)

    with pytest.raises(ValueError, match="needs a note"):
        recover(repo, record.id, action=RESUME, note=" ")
    with pytest.raises(ValueError, match="action must be resume or abandon"):
        recover(repo, record.id, action="ignore", note="x")


def test_only_a_running_execution_can_be_recovered(repo: MarkdownRepository) -> None:
    record = _running(repo)
    move(repo, record.id, "blocked", reason="Down")

    with pytest.raises(ExecutionError, match="only a running execution"):
        recover(repo, record.id, action=RESUME, note="x")


def test_a_leftover_temporary_file_does_not_disturb_the_project(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    (repo.root / "executions" / "tmpabc123.tmp").write_text("partial", encoding="utf-8")

    assert repo.record_ids("EXEC") == [record.id]
    assert repo.list_records("EXEC").errors == ()


def test_a_step_left_open_before_the_last_one_is_rejected(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    start_step(repo, record.id, 1, "Open")
    finish_step(repo, record.id, 1, "passed")
    start_step(repo, record.id, 2, "Submit")
    finish_step(repo, record.id, 2, "passed")
    text = record.path.read_text(encoding="utf-8")
    lines = text.splitlines()
    index = next(i for i, ln in enumerate(lines) if "outcome: passed" in ln)
    del lines[index]
    record.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(
        RecordValidationError, match="no outcome but it is not the last"
    ):
        repo.get(record.id)


# --- never overwritten --------------------------------------------------------


def _finalized_failure(repo: MarkdownRepository):
    record = _running(repo, environment="production-like")
    _fail(repo, record.id, failure_type="product")
    return move(repo, record.id, "finalized")


def test_rerunning_creates_a_new_execution_and_keeps_the_original(
    repo: MarkdownRepository,
) -> None:
    original = _finalized_failure(repo)
    before = original.path.read_text(encoding="utf-8")

    again = rerun(repo, original.id, executor="Bruno")

    assert again.id == "EXEC-002"
    assert again.metadata["rerun_of"] == original.id
    assert again.metadata["status"] == "created"
    assert again.metadata["executor"] == "Bruno"
    assert again.metadata["environment"] == "production-like"
    assert again.metadata["test_case"] == "TC-001"
    assert original.path.read_text(encoding="utf-8") == before
    assert repo.verify(original.id) == []


def test_a_rerun_keeps_the_executor_by_default(repo: MarkdownRepository) -> None:
    original = _finalized_failure(repo)

    assert rerun(repo, original.id).metadata["executor"] == "Ana"


@pytest.mark.parametrize("state", ["created", "planned", "running"])
def test_only_an_execution_with_a_result_can_be_rerun(
    repo: MarkdownRepository, state: str
) -> None:
    record = create_execution(
        repo,
        execution_type="manual",
        executor="Ana",
        environment="staging",
        test_case="TC-001",
    )
    if state in {"planned", "running"}:
        move(repo, record.id, "planned")
    if state == "running":
        move(repo, record.id, "running")

    with pytest.raises(ExecutionError, match="only an execution with a result"):
        rerun(repo, record.id)


def test_a_result_that_is_not_finalized_yet_can_be_rerun(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)
    move(repo, record.id, "blocked", reason="Down")

    assert rerun(repo, record.id).metadata["rerun_of"] == record.id


# --- corrections --------------------------------------------------------------


def test_a_finalized_execution_is_corrected_with_a_separate_event(
    repo: MarkdownRepository,
) -> None:
    original = _finalized_failure(repo)
    before = original.path.read_text(encoding="utf-8")

    event = record_correction(
        repo,
        original.id,
        author="Ana",
        justification="The environment was staging, not production-like.",
        details={"environment": "staging"},
    )
    note = record_correction(
        repo, original.id, author="Bruno", justification="Linked later.", addition=True
    )

    assert (event.kind, event.author) == ("correction", "Ana")
    assert note.kind == "addition"
    assert original.path.read_text(encoding="utf-8") == before
    assert [e.kind for e in repo.history(original.id)] == [
        "sealed",
        "correction",
        "addition",
    ]
    assert repo.verify(original.id) == []


def test_corrections_need_the_execution_to_be_finalized(
    repo: MarkdownRepository,
) -> None:
    record = _running(repo)

    with pytest.raises(ValueError, match="is not finalized"):
        record_correction(repo, record.id, author="Ana", justification="x")
