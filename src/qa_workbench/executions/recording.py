"""Record an execution step by step (REQ-019).

Each call writes the record to disk before returning, so the file always shows
what happened so far. A step is saved as *in progress* before it is carried out
and completed afterwards; if the process dies in between, recovery finds the
step still in progress instead of a result nobody observed.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from qa_workbench.executions.schema import FAILURE_TYPES, STEP_OUTCOMES
from qa_workbench.executions.service import ExecutionError, render_body
from qa_workbench.executions.states import State
from qa_workbench.storage.repository import MarkdownRepository, Record


def _now() -> datetime:
    return datetime.now().astimezone()


def _running(repository: MarkdownRepository, execution_id: str) -> Record:
    record = repository.get(execution_id)
    status = record.metadata["status"]
    if status != State.RUNNING.value:
        raise ExecutionError(
            f"{execution_id} is {status}; steps can only be recorded while it is "
            "running."
        )
    return record


def _save(
    repository: MarkdownRepository, record: Record, changes: dict[str, Any]
) -> Record:
    body = render_body({**record.metadata, **changes})
    return repository.update(record.id, changes, body)


def check_preconditions(
    repository: MarkdownRepository,
    execution_id: str,
    checks: Sequence[tuple[str, bool]],
) -> Record:
    """Record which preconditions were verified, and whether each one held."""
    record = repository.get(execution_id)
    status = record.metadata["status"]
    if status not in {State.RUNNING.value, State.PLANNED.value}:
        raise ExecutionError(
            f"{execution_id} is {status}; preconditions are checked while it is "
            "planned or running."
        )
    items = [{"text": text.strip(), "checked": bool(ok)} for text, ok in checks]
    return _save(repository, record, {"preconditions_checked": items})


def start_step(
    repository: MarkdownRepository, execution_id: str, number: int, action: str
) -> Record:
    """Save a step as in progress, before it is carried out."""
    record = _running(repository, execution_id)
    steps = list(record.metadata.get("steps_executed") or [])
    if steps and steps[-1].get("outcome") is None:
        raise ExecutionError(
            f"Step {steps[-1]['number']} is still in progress; finish it before "
            "starting another."
        )
    if number != len(steps) + 1:
        raise ExecutionError(f"The next step is number {len(steps) + 1}, not {number}.")
    if not action.strip():
        raise ValueError("A step needs an action.")
    steps.append({"number": number, "action": action.strip(), "started_at": _now()})
    return _save(repository, record, {"steps_executed": steps})


def finish_step(
    repository: MarkdownRepository,
    execution_id: str,
    number: int,
    outcome: str,
    *,
    observed: str = "",
    evidence: Sequence[str] = (),
    failure_type: str | None = None,
) -> Record:
    """Complete the step that is in progress with what was actually observed."""
    if outcome not in STEP_OUTCOMES:
        raise ValueError(f"outcome must be one of: {', '.join(sorted(STEP_OUTCOMES))}.")
    if failure_type is not None and failure_type not in FAILURE_TYPES:
        raise ValueError(
            f"failure_type must be one of: {', '.join(sorted(FAILURE_TYPES))}."
        )
    record = _running(repository, execution_id)
    steps = [dict(step) for step in record.metadata.get("steps_executed") or []]
    if (
        not steps
        or steps[-1].get("outcome") is not None
        or steps[-1]["number"] != number
    ):
        raise ExecutionError(f"Step {number} is not the step in progress.")
    if evidence and "EVD" in repository.prefixes:
        missing = sorted(set(evidence) - set(repository.record_ids("EVD")))
        if missing:
            raise ExecutionError(f"This evidence does not exist: {', '.join(missing)}.")
    step = steps[-1]
    step["finished_at"] = _now()
    step["outcome"] = outcome
    if observed.strip():
        step["observed"] = observed.strip()
    if evidence:
        step["evidence"] = list(evidence)
    if failure_type:
        step["failure_type"] = failure_type
    return _save(repository, record, {"steps_executed": steps})
