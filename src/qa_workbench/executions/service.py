"""Create executions and move them through the lifecycle (REQ-017, REQ-018)."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from qa_workbench.executions.schema import EXPLORATORY, MACHINE_TYPES
from qa_workbench.executions.states import (
    RESULT_STATES,
    State,
    parse_state,
    validate_transition,
)
from qa_workbench.storage.repository import MarkdownRepository, Record

ACTIVE = "active"


class ExecutionError(Exception):
    """Raised when an execution cannot be created or moved."""


def _now() -> datetime:
    return datetime.now().astimezone()


def _step_line(step: Mapping[str, Any]) -> str:
    outcome = step.get("outcome") or "in progress"
    line = f"{step.get('number', '?')}. {step.get('action', '')} - {outcome}"
    if step.get("observed"):
        line += f": {step['observed']}"
    return line


def render_body(metadata: Mapping[str, Any]) -> str:
    """The readable record of an execution, built from its fields."""

    def section(heading: str, text: object) -> str:
        return f"## {heading}\n\n{str(text).strip()}" if text else f"## {heading}"

    evidence = metadata.get("evidence") or []
    listed = "\n".join(f"- {item}" for item in evidence) if evidence else ""
    case = metadata.get("test_case")
    conclusion = metadata.get("reason") or metadata.get("result") or ""
    steps = metadata.get("steps_executed") or []
    executed = "\n".join(_step_line(s) for s in steps if isinstance(s, dict))
    return (
        "\n\n".join(
            [
                f"# {metadata.get('id', 'Execution')}",
                section("Objective", f"Validate {case}." if case else ""),
                section("Executed steps", executed),
                section("Expected result", metadata.get("expected_result")),
                section("Observed result", metadata.get("observed_result")),
                section("Evidence", listed),
                section("Notes", metadata.get("notes")),
                section("Conclusion", conclusion),
            ]
        )
        + "\n"
    )


def create_execution(
    repository: MarkdownRepository,
    *,
    execution_type: str,
    executor: str,
    environment: str,
    test_case: str | None = None,
    plan: str | None = None,
    suite: str | None = None,
    project: str | None = None,
    version: str | None = None,
    branch: str | None = None,
    commit: str | None = None,
    automation_tool: str | None = None,
    requires_approval: bool = False,
    rerun_of: str | None = None,
) -> Record:
    """Create an execution in the ``created`` state.

    A test case must exist and be active, except for exploratory sessions. Its
    expected result is copied into the execution, so the record keeps what was
    expected at the time even if the case changes later.
    """
    snapshot: dict[str, Any] = {}
    if test_case is not None and "TC" in repository.prefixes:
        if test_case not in set(repository.record_ids("TC")):
            raise ExecutionError(f"The test case {test_case} does not exist.")
        case = repository.get(test_case)
        if case.metadata["status"] != ACTIVE and execution_type != EXPLORATORY:
            raise ExecutionError(
                f"{test_case} is {case.metadata['status']}; only an active test "
                "case can be executed."
            )
        if case.metadata.get("expected_result"):
            snapshot["expected_result"] = case.metadata["expected_result"]
    fields: dict[str, Any] = {
        "status": State.CREATED.value,
        "execution_type": execution_type,
        "executor": executor.strip(),
        "environment": environment.strip(),
        **snapshot,
    }
    optional: dict[str, Any] = {
        "test_case": test_case,
        "plan": plan,
        "suite": suite,
        "project": project,
        "version": version,
        "branch": branch,
        "commit": commit,
        "automation_tool": automation_tool,
        "requires_approval": True if requires_approval else None,
        "rerun_of": rerun_of,
    }
    fields.update({key: value for key, value in optional.items() if value})
    return repository.create("EXEC", fields, render_body)


def move(
    repository: MarkdownRepository,
    execution_id: str,
    target: str,
    *,
    observed_result: str | None = None,
    reason: str | None = None,
    evidence: Sequence[str] = (),
    bugs: Sequence[str] = (),
    notes: str | None = None,
    approved_by: str | None = None,
    failure_type: str | None = None,
) -> Record:
    """Move an execution to ``target`` after checking the lifecycle and the data.

    Moving to ``running`` records the start time, moving to a result records the
    finish time, duration, and result, and moving to ``finalized`` seals the
    record: it can never be edited again.
    """
    record = repository.get(execution_id)
    metadata = record.metadata
    current = parse_state(metadata["status"])
    new = parse_state(target)
    validate_transition(
        current,
        new,
        requires_approval=bool(metadata.get("requires_approval")),
    )

    now = _now()
    changes: dict[str, Any] = {"status": new.value}
    if (
        current is State.AWAITING_APPROVAL
        and new is State.RUNNING
        and metadata.get("requires_approval")
    ):
        if not (approved_by and approved_by.strip()):
            raise ExecutionError(
                "Approval needs approved_by: the name of the person who approves."
            )
        if (
            metadata["execution_type"] in MACHINE_TYPES
            and approved_by.strip().lower() == str(metadata["executor"]).lower()
        ):
            raise ExecutionError("The approver must be different from the executor.")
        changes["approved_by"] = approved_by.strip()
        changes["approved_at"] = now
    if new is State.RUNNING:
        changes["started_at"] = now
    if new in RESULT_STATES:
        changes["result"] = new.value
        changes["finished_at"] = now
        started = metadata.get("started_at")
        if isinstance(started, datetime):
            changes["duration_seconds"] = round((now - started).total_seconds(), 3)
    _check_evidence_exists(repository, evidence)
    optional: dict[str, Any] = {
        "observed_result": observed_result.strip() if observed_result else None,
        "reason": reason.strip() if reason else None,
        "evidence": [*(metadata.get("evidence") or []), *evidence] or None,
        "bugs": [*(metadata.get("bugs") or []), *bugs] or None,
        "notes": notes.strip() if notes else None,
        "failure_type": failure_type,
    }
    changes.update({key: value for key, value in optional.items() if value})
    return repository.update(
        execution_id, changes, render_body({**metadata, **changes})
    )


def _check_evidence_exists(
    repository: MarkdownRepository, evidence: Sequence[str]
) -> None:
    """Evidence is never invented: every cited id must be a record that exists."""
    if not evidence or "EVD" not in repository.prefixes:
        return
    existing = set(repository.record_ids("EVD"))
    missing = sorted(e for e in evidence if e not in existing)
    if missing:
        raise ExecutionError(f"This evidence does not exist: {', '.join(missing)}.")
