"""Execution records (REQ-017, REQ-018).

The checks tie an execution's data to its state, so an execution cannot claim a
pass without evidence, a block without a reason, or a finish without a time, and
automation driven by an agent cannot be recorded as a manual run.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from qa_workbench.executions.states import RESULT_NAMES, STATUS_NAMES, State
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


def check_execution(metadata: Mapping[str, Any]) -> list[str]:
    """Rules tying an execution's data to its state."""
    return (
        _check_type(metadata)
        + _check_result(metadata)
        + _check_times(metadata)
        + _check_approval(metadata)
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
    },
    choices={"execution_type": EXECUTION_TYPES, "result": RESULT_NAMES},
    text_lists=(),
    extra_checks=(check_execution,),
)
