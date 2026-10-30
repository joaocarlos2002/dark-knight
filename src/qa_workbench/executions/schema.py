"""Execution records (REQ-017, REQ-018).

The checks tie an execution's data to its state, so an execution cannot claim a
pass without evidence, a block without a reason, or a finish without a time, and
automation driven by an agent cannot be recorded as a manual run.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from qa_workbench.executions.states import RESULT_NAMES, STATUS_NAMES, State
from qa_workbench.storage.ids import parse_id
from qa_workbench.storage.validation import RecordSchema

MANUAL = "manual"
ASSISTED_MANUAL = "assisted_manual"
AGENT_DRIVEN = "agent_driven"
AUTOMATED = "automated"
EXPLORATORY = "exploratory"
EXECUTION_TYPES = frozenset(
    {MANUAL, ASSISTED_MANUAL, AGENT_DRIVEN, AUTOMATED, EXPLORATORY}
)
HUMAN_TYPES = frozenset({MANUAL, ASSISTED_MANUAL})
MACHINE_TYPES = frozenset({AGENT_DRIVEN, AUTOMATED})

PRODUCT = "product"
FAILURE_TYPES = frozenset({PRODUCT, "test", "infrastructure", "evidence_collection"})
STEP_OUTCOMES = frozenset({"passed", "failed", "blocked", "skipped", "interrupted"})
_STEP_KEYS = {
    "number",
    "action",
    "started_at",
    "finished_at",
    "outcome",
    "observed",
    "evidence",
    "failure_type",
}
_NOT_STARTED = {State.CREATED.value, State.PLANNED.value, State.AWAITING_APPROVAL.value}
_NEEDS_REASON = {
    State.BLOCKED.value,
    State.INCONCLUSIVE.value,
    State.CANCELLED.value,
}


def _text(metadata: Mapping[str, Any], key: str) -> str:
    return str(metadata.get(key) or "").strip()


def _check_type(metadata: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    kind = metadata.get("execution_type")
    tool = _text(metadata, "automation_tool")
    if kind in HUMAN_TYPES and tool:
        problems.append(
            f"a {kind} execution cannot name an automation tool; automation driven "
            "by an agent or a runner is agent_driven or automated."
        )
    if kind in MACHINE_TYPES and not tool:
        problems.append(
            f"a {kind} execution needs automation_tool (for example playwright)."
        )
    if kind != EXPLORATORY and not _text(metadata, "test_case"):
        problems.append("test_case is required (except for exploratory executions).")
    approval = metadata.get("requires_approval")
    if approval is not None and not isinstance(approval, bool):
        problems.append("requires_approval must be true or false.")
    return problems


def _check_result(metadata: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    status = metadata.get("status")
    result = metadata.get("result")
    if status in RESULT_NAMES and result != status:
        problems.append(f"result must be {status} while the status is {status}.")
    elif status == State.FINALIZED.value and result not in RESULT_NAMES:
        problems.append(
            f"a finalized execution needs a result: {', '.join(sorted(RESULT_NAMES))}."
        )
    elif status in _NOT_STARTED | {State.RUNNING.value} and result is not None:
        problems.append(f"an execution that is {status} has no result yet.")
    effective = result if status == State.FINALIZED.value else status
    if effective == State.PASSED.value:
        evidence = metadata.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            problems.append("a passed execution needs evidence.")
        if not _text(metadata, "observed_result"):
            problems.append("a passed execution needs the observed result.")
    elif effective == State.FAILED.value and not _text(metadata, "observed_result"):
        problems.append("a failed execution needs the observed result.")
    elif effective in _NEEDS_REASON and not _text(metadata, "reason"):
        problems.append(f"a {effective} execution needs a reason.")
    return problems


def _check_times(metadata: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    status = metadata.get("status")
    result = metadata.get("result")
    started = metadata.get("started_at")
    finished = metadata.get("finished_at")
    ran = status not in _NOT_STARTED
    cancelled_early = status == State.CANCELLED.value or (
        status == State.FINALIZED.value and result == State.CANCELLED.value
    )
    if ran and not cancelled_early and started is None:
        problems.append(f"an execution that is {status} needs started_at.")
    done = status in RESULT_NAMES or status == State.FINALIZED.value
    if done and finished is None:
        problems.append(f"an execution that is {status} needs finished_at.")
    if (
        isinstance(started, datetime)
        and isinstance(finished, datetime)
        and finished < started
    ):
        problems.append("finished_at cannot be earlier than started_at.")
    return problems


def _check_approval(metadata: Mapping[str, Any]) -> list[str]:
    if metadata.get("requires_approval") is not True:
        return []
    status = metadata.get("status")
    if status in _NOT_STARTED or metadata.get("started_at") is None:
        return []
    problems: list[str] = []
    approver = _text(metadata, "approved_by")
    if not approver or metadata.get("approved_at") is None:
        problems.append(
            "this execution requires approval: approved_by and approved_at must "
            "be recorded before it runs."
        )
    elif (
        metadata.get("execution_type") in MACHINE_TYPES
        and approver.lower() == _text(metadata, "executor").lower()
    ):
        problems.append("the approver must be different from the executor.")
    return problems


def _aware(value: Any) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None


def _check_step(number: int, step: Any, last: bool, status: Any) -> list[str]:
    if not isinstance(step, dict):
        return [f"step {number} must be a mapping."]
    problems: list[str] = []
    extra = set(step) - _STEP_KEYS
    if extra:
        problems.append(f"step {number} has unknown fields: {sorted(extra)}.")
    if step.get("number") != number:
        problems.append(
            f"step {number} is numbered {step.get('number')!r}; steps are numbered "
            "1, 2, 3... in order."
        )
    if not _text(step, "action"):
        problems.append(f"step {number} needs an action.")
    if not _aware(step.get("started_at")):
        problems.append(f"step {number} needs started_at with a timezone.")
    finished = step.get("finished_at")
    if finished is not None and not _aware(finished):
        problems.append(f"step {number}: finished_at needs a timezone.")
    elif (
        _aware(finished)
        and _aware(step.get("started_at"))
        and finished < step["started_at"]
    ):
        problems.append(f"step {number} finished before it started.")
    outcome = step.get("outcome")
    if outcome is None:
        if not last:
            problems.append(
                f"step {number} has no outcome but it is not the last step."
            )
        elif status != State.RUNNING.value:
            problems.append(
                f"step {number} is still in progress but the execution is {status}."
            )
    elif outcome not in STEP_OUTCOMES:
        problems.append(
            f"step {number}: outcome {outcome!r} is not allowed; use one of: "
            f"{', '.join(sorted(STEP_OUTCOMES))}."
        )
    if outcome == "failed":
        if not _text(step, "observed"):
            problems.append(f"failed step {number} needs the observed result.")
        if step.get("failure_type") not in FAILURE_TYPES:
            problems.append(f"failed step {number} needs a failure_type.")
    kind = step.get("failure_type")
    if kind is not None and kind not in FAILURE_TYPES:
        problems.append(f"step {number}: failure_type {kind!r} is not allowed.")
    for item in step.get("evidence") or []:
        try:
            if parse_id(str(item)).prefix != "EVD":
                problems.append(f"step {number}: {item} is not an evidence id.")
        except ValueError:
            problems.append(f"step {number}: {item!r} is not an evidence id.")
    return problems


def _check_steps_record(metadata: Mapping[str, Any]) -> list[str]:
    steps = metadata.get("steps_executed")
    if steps is None:
        return []
    if not isinstance(steps, list):
        return ["steps_executed must be a list."]
    status = metadata.get("status")
    problems: list[str] = []
    for number, step in enumerate(steps, start=1):
        problems += _check_step(number, step, number == len(steps), status)
    effective = metadata.get("result") if status == State.FINALIZED.value else status
    if effective == State.PASSED.value:
        bad = [
            index
            for index, step in enumerate(steps, start=1)
            if isinstance(step, dict)
            and step.get("outcome") not in {"passed", "skipped"}
        ]
        if bad:
            problems.append(
                f"a passed execution cannot have steps that did not pass (step "
                f"{', '.join(map(str, bad))})."
            )
    return problems


def _check_failures(metadata: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    kind = metadata.get("failure_type")
    if kind is not None and kind not in FAILURE_TYPES:
        problems.append(
            f"failure_type {kind!r} is not allowed; use one of: "
            f"{', '.join(sorted(FAILURE_TYPES))}."
        )
    status = metadata.get("status")
    effective = metadata.get("result") if status == State.FINALIZED.value else status
    if effective == State.FAILED.value and kind is None:
        problems.append(
            "a failed execution needs a failure_type: product, test, "
            "infrastructure, or evidence_collection."
        )
    if metadata.get("bugs") and kind != PRODUCT:
        problems.append(
            "bugs can only be linked to a product failure; record infrastructure, "
            "test, and evidence-collection problems without a defect."
        )
    return problems


def _check_recoveries(metadata: Mapping[str, Any]) -> list[str]:
    items = metadata.get("recoveries")
    if items is None:
        return []
    if not isinstance(items, list):
        return ["recoveries must be a list."]
    problems: list[str] = []
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            problems.append(f"recovery {number} must be a mapping.")
            continue
        if item.get("action") not in {"resume", "abandon"}:
            problems.append(f"recovery {number}: action must be resume or abandon.")
        if not _text(item, "note"):
            problems.append(f"recovery {number} needs a note.")
        if not _aware(item.get("timestamp")):
            problems.append(f"recovery {number} needs a timestamp with a timezone.")
    return problems


def _check_preconditions(metadata: Mapping[str, Any]) -> list[str]:
    items = metadata.get("preconditions_checked")
    if items is None:
        return []
    if not isinstance(items, list):
        return ["preconditions_checked must be a list."]
    problems: list[str] = []
    for number, item in enumerate(items, start=1):
        if (
            not isinstance(item, dict)
            or not _text(item, "text")
            or not isinstance(item.get("checked"), bool)
        ):
            problems.append(
                f"precondition {number} needs a text and checked true/false."
            )
    return problems


def check_execution(metadata: Mapping[str, Any]) -> list[str]:
    """Rules tying an execution's data to its state."""
    return (
        _check_type(metadata)
        + _check_result(metadata)
        + _check_times(metadata)
        + _check_approval(metadata)
        + _check_steps_record(metadata)
        + _check_failures(metadata)
        + _check_preconditions(metadata)
        + _check_recoveries(metadata)
    )


EXECUTION_SCHEMA = RecordSchema(
    prefix="EXEC",
    directory="executions",
    statuses=frozenset(STATUS_NAMES),
    required=("execution_type", "executor", "environment"),
    optional_timestamps=("started_at", "finished_at", "approved_at"),
    immutable_statuses=frozenset({State.FINALIZED.value}),
    references={
        "test_case": ("TC",),
        "plan": ("TP",),
        "suite": ("SUITE",),
        "project": ("PROJ",),
        "evidence": ("EVD",),
        "bugs": ("BUG",),
        "rerun_of": ("EXEC",),
    },
    choices={
        "execution_type": EXECUTION_TYPES,
        "result": RESULT_NAMES,
    },
    text_lists=(),
    extra_checks=(check_execution,),
)
