"""Recover interrupted executions, rerun, and record corrections (REQ-019).

* An execution that stays ``running`` without activity was probably cut short.
  ``find_interrupted`` lists them; ``recover`` either resumes (the unfinished
  step is closed as interrupted and must be run again) or abandons it as
  ``inconclusive``. It never invents an outcome for a step nobody observed.
* A previous execution is never overwritten: ``rerun`` creates a new execution
  that points back to the one it repeats.
* After finalization, corrections and additions are separate history events.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from qa_workbench.executions.service import (
    ExecutionError,
    create_execution,
    move,
    render_body,
)
from qa_workbench.executions.states import RESULT_NAMES, State
from qa_workbench.storage.history import HistoryEvent
from qa_workbench.storage.repository import MarkdownRepository, Record

RESUME = "resume"
ABANDON = "abandon"


@dataclass(frozen=True)
class Interrupted:
    """A running execution with no recent activity."""

    id: str
    last_activity: datetime
    steps_done: int
    step_in_progress: int | None


def _now() -> datetime:
    return datetime.now().astimezone()


def find_interrupted(
    repository: MarkdownRepository,
    *,
    idle_for: timedelta,
    now: datetime | None = None,
) -> list[Interrupted]:
    """Running executions whose last write is older than ``idle_for``."""
    if idle_for <= timedelta(0):
        raise ValueError("idle_for must be longer than zero.")
    moment = now or _now()
    found: list[Interrupted] = []
    for record in repository.list_records("EXEC").records:
        metadata = record.metadata
        if metadata["status"] != State.RUNNING.value:
            continue
        if moment - metadata["updated_at"] < idle_for:
            continue
        steps = metadata.get("steps_executed") or []
        open_step = (
            steps[-1]["number"] if steps and steps[-1].get("outcome") is None else None
        )
        done = len(steps) - (1 if open_step is not None else 0)
        found.append(Interrupted(record.id, metadata["updated_at"], done, open_step))
    return found


def recover(
    repository: MarkdownRepository, execution_id: str, *, action: str, note: str
) -> Record:
    """Resume or abandon an interrupted execution, recording what happened.

    The step that was in progress is closed as ``interrupted``. Resuming keeps the
    execution running so the step can be repeated; abandoning ends it as
    ``inconclusive``, keeping the steps that did finish.
    """
    if action not in {RESUME, ABANDON}:
        raise ValueError(f"action must be {RESUME} or {ABANDON}.")
    if not note.strip():
        raise ValueError("Recovery needs a note saying what happened.")
    record = repository.get(execution_id)
    metadata = record.metadata
    if metadata["status"] != State.RUNNING.value:
        raise ExecutionError(
            f"{execution_id} is {metadata['status']}; only a running execution "
            "can be recovered."
        )
    steps = [dict(step) for step in metadata.get("steps_executed") or []]
    interrupted_step: int | None = None
    if steps and steps[-1].get("outcome") is None:
        interrupted_step = steps[-1]["number"]
        steps[-1]["outcome"] = "interrupted"
        steps[-1]["finished_at"] = _now()
        steps[-1]["observed"] = (
            "Interrupted before it finished; the outcome was not observed."
        )
    entry: dict[str, Any] = {
        "timestamp": _now(),
        "action": action,
        "note": note.strip(),
    }
    if interrupted_step is not None:
        entry["interrupted_step"] = interrupted_step
    changes: dict[str, Any] = {
        "steps_executed": steps,
        "recoveries": [*(metadata.get("recoveries") or []), entry],
    }
    updated = repository.update(
        execution_id, changes, render_body({**metadata, **changes})
    )
    if action == ABANDON:
        return move(
            repository,
            execution_id,
            State.INCONCLUSIVE.value,
            reason=f"Interrupted and abandoned: {note.strip()}",
        )
    return updated


def rerun(
    repository: MarkdownRepository, execution_id: str, *, executor: str | None = None
) -> Record:
    """Start a new execution that repeats a finished one. The original is kept."""
    source = repository.get(execution_id).metadata
    status = source["status"]
    if status not in RESULT_NAMES and status != State.FINALIZED.value:
        raise ExecutionError(
            f"{execution_id} is {status}; only an execution with a result can be rerun."
        )
    return create_execution(
        repository,
        execution_type=source["execution_type"],
        executor=executor or source["executor"],
        environment=source["environment"],
        test_case=source.get("test_case"),
        plan=source.get("plan"),
        suite=source.get("suite"),
        project=source.get("project"),
        version=source.get("version"),
        branch=source.get("branch"),
        automation_tool=source.get("automation_tool"),
        requires_approval=bool(source.get("requires_approval")),
        rerun_of=execution_id,
    )


def record_correction(
    repository: MarkdownRepository,
    execution_id: str,
    *,
    author: str,
    justification: str,
    details: Mapping[str, Any] | None = None,
    addition: bool = False,
) -> HistoryEvent:
    """Record a correction (or an addition) to a finalized execution.

    The execution itself is not changed: the event is appended to its history
    with who, when, and why.
    """
    return repository.add_history_event(
        execution_id,
        "addition" if addition else "correction",
        author,
        justification,
        details,
    )
