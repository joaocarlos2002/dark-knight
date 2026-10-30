"""Test plan records (REQ-014, REQ-016)."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from qa_workbench.core.secrets import find_secrets
from qa_workbench.review.policy import ReviewPolicy, review_checks
from qa_workbench.storage.ids import parse_id
from qa_workbench.storage.validation import RecordSchema

DRAFT = "draft"
STATUSES = frozenset(
    {
        DRAFT,
        "in_review",
        "approved",
        "rejected",
        "in_progress",
        "completed",
        "cancelled",
    }
)
ORIGINS = frozenset({"manual", "ai"})
REVIEW_POLICY = ReviewPolicy(approved_status="approved", rejected_status="rejected")

RISK_LEVELS = frozenset({"high", "medium", "low"})
INCLUDE = "include"
EXCLUDE = "exclude"
DECISIONS = (INCLUDE, EXCLUDE)
FACTORS = (
    "changed_requirements",
    "affected_features",
    "defect_history",
    "dependencies",
    "criticality",
    "coverage",
    "time",
    "regression_risk",
    "previous_results",
    "readiness",
)
SELECTION_SOURCES = ("manual", "rules", "ai")


def _check_risks(metadata: Mapping[str, Any]) -> list[str]:
    risks = metadata.get("risks")
    if risks is None:
        return []
    if not isinstance(risks, list):
        return ["risks must be a list."]
    problems: list[str] = []
    for number, risk in enumerate(risks, start=1):
        if not isinstance(risk, dict):
            problems.append(f"risk {number} must have a description and a level.")
            continue
        description = risk.get("description")
        if not isinstance(description, str) or not description.strip():
            problems.append(f"risk {number} needs a description.")
        if risk.get("level") not in RISK_LEVELS:
            problems.append(
                f"risk {number}: level {risk.get('level')!r} is not allowed; use one "
                f"of: {', '.join(sorted(RISK_LEVELS))}."
            )
        mitigation = risk.get("mitigation", "")
        if mitigation is not None and not isinstance(mitigation, str):
            problems.append(f"risk {number}: mitigation must be text.")
        extra = set(risk) - {"description", "level", "mitigation"}
        if extra:
            problems.append(f"risk {number} has unknown fields: {sorted(extra)}.")
    return problems


def _check_schedule(metadata: Mapping[str, Any]) -> list[str]:
    schedule = metadata.get("schedule")
    if schedule is None:
        return []
    if not isinstance(schedule, dict):
        return ["schedule must have a start and an end."]
    problems: list[str] = []
    stamps: dict[str, datetime] = {}
    for key in ("start", "end"):
        value = schedule.get(key)
        if not isinstance(value, datetime) or value.tzinfo is None:
            problems.append(
                f"schedule {key} must be an ISO 8601 timestamp with a timezone."
            )
        else:
            stamps[key] = value
    extra = set(schedule) - {"start", "end"}
    if extra:
        problems.append(f"schedule has unknown fields: {sorted(extra)}.")
    if len(stamps) == 2 and stamps["end"] < stamps["start"]:
        problems.append("schedule end cannot be earlier than its start.")
    return problems


def _check_selection(metadata: Mapping[str, Any]) -> list[str]:
    selection = metadata.get("selection")
    if selection is None:
        return []
    if not isinstance(selection, list):
        return ["selection must be a list."]
    problems: list[str] = []
    seen: set[str] = set()
    for number, item in enumerate(selection, start=1):
        if not isinstance(item, dict):
            problems.append(f"selection {number} must have an id and a decision.")
            continue
        record_id = item.get("id")
        try:
            prefix = parse_id(str(record_id)).prefix
        except ValueError:
            problems.append(f"selection {number}: {record_id!r} is not a record id.")
        else:
            if prefix not in {"TC", "SUITE"}:
                problems.append(
                    f"selection {number}: only TC and SUITE can be selected, got "
                    f"{record_id}."
                )
            if record_id in seen:
                problems.append(f"{record_id} appears more than once in the selection.")
            seen.add(str(record_id))
        if item.get("decision") not in DECISIONS:
            problems.append(
                f"selection {number}: decision {item.get('decision')!r} is not "
                f"allowed; use {INCLUDE} or {EXCLUDE}."
            )
        source = item.get("source", "manual")
        if source not in SELECTION_SOURCES:
            problems.append(
                f"selection {number}: source {source!r} is not allowed; use one "
                f"of: {', '.join(SELECTION_SOURCES)}."
            )
        reasons = item.get("reasons")
        if not isinstance(reasons, list) or not reasons:
            problems.append(
                f"selection {number} ({record_id}) needs at least one reason: every "
                "inclusion and exclusion must be justified."
            )
            continue
        for reason in reasons:
            if not isinstance(reason, dict) or reason.get("factor") not in FACTORS:
                problems.append(
                    f"selection {number}: a reason needs a factor from: "
                    f"{', '.join(FACTORS)}."
                )
            elif not str(reason.get("detail") or "").strip():
                problems.append(
                    f"selection {number}: the {reason['factor']} reason needs a detail."
                )
    return problems


def _check_data_for_secrets(metadata: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    for name in ("data", "strategy", "scope"):
        value = metadata.get(name)
        texts = value if isinstance(value, list) else [value]
        for item in texts:
            for description in find_secrets(str(item or "")):
                problems.append(
                    f"{name} contains {description}; reference it by name instead, "
                    "for example $TEST_PASSWORD."
                )
    return problems


def _check_required_lists(metadata: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    for name in ("objectives", "entry_criteria", "exit_criteria"):
        value = metadata.get(name)
        if not isinstance(value, list) or not value:
            problems.append(f"{name} needs at least one item.")
    return problems


def check_plan(metadata: Mapping[str, Any]) -> list[str]:
    """Rules of a test plan that a schema cannot express declaratively."""
    return (
        _check_risks(metadata)
        + _check_schedule(metadata)
        + _check_selection(metadata)
        + _check_data_for_secrets(metadata)
    )


TEST_PLAN_SCHEMA = RecordSchema(
    prefix="TP",
    directory="test-plans",
    statuses=STATUSES,
    required=("title", "origin", "scope", "strategy"),
    references={"suites": ("SUITE",)},
    choices={"origin": ORIGINS},
    text_lists=(
        "objectives",
        "in_scope",
        "out_of_scope",
        "levels",
        "test_types",
        "environments",
        "profiles",
        "data",
        "dependencies",
        "entry_criteria",
        "exit_criteria",
        "owners",
    ),
    extra_checks=(
        _check_required_lists,
        check_plan,
        review_checks(REVIEW_POLICY),
    ),
)
