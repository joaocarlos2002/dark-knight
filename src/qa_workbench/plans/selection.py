"""Explainable test selection (REQ-016).

``recommend`` proposes which test cases to run and says why for every one, using
only data that exists: the requirements that changed, each case's status,
priority, criticality, and time estimate, and requirement coverage. It states
what it could not consider. The result is a proposal: the user can edit it, and
the plan stores it with its reasons so it can be checked later.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from qa_workbench.storage.repository import MarkdownRepository, Record

ACTIVE = "active"
HIGH_CRITICALITY = {"critical", "major"}
BASELINE_TYPES = {"smoke", "sanity"}

NOT_CONSIDERED = (
    "defect_history: no defect records exist yet, so it was not considered.",
    "previous_results: no executions exist yet, so it was not considered.",
    "dependencies: test cases do not declare dependencies yet, so they were not "
    "considered.",
)


@dataclass(frozen=True)
class Reason:
    factor: str
    detail: str


@dataclass(frozen=True)
class SelectionItem:
    """One inclusion or exclusion, with the reasons for it."""

    id: str
    decision: str
    reasons: tuple[Reason, ...]
    source: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "decision": self.decision,
            "source": self.source,
            "reasons": [
                {"factor": reason.factor, "detail": reason.detail}
                for reason in self.reasons
            ],
        }


@dataclass(frozen=True)
class Recommendation:
    items: tuple[SelectionItem, ...]
    notes: tuple[str, ...] = field(default=NOT_CONSIDERED)
    minutes_used: int = 0

    def included(self) -> list[SelectionItem]:
        return [item for item in self.items if item.decision == "include"]

    def to_fields(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.items]


def _score(case: Record, related: bool) -> tuple[int, int, int, str]:
    priority = {"high": 0, "medium": 1, "low": 2}.get(
        str(case.metadata.get("priority")), 3
    )
    critical = 0 if case.metadata.get("criticality") in HIGH_CRITICALITY else 1
    return (0 if related else 1, critical, priority, case.id)


def recommend(
    repository: MarkdownRepository,
    *,
    changed_requirements: Iterable[str] = (),
    time_budget_minutes: int | None = None,
) -> Recommendation:
    """Recommend a selection of test cases and justify each decision.

    Only ``active`` (approved) cases are eligible. A case is included when it
    covers a changed requirement, is critical or high priority, is the only case
    covering a requirement, or is a smoke or sanity baseline. With a time budget,
    the most relevant cases are kept until it is used up; cases without an
    estimate are included but not counted against it.
    """
    changed = set(changed_requirements)
    if time_budget_minutes is not None and time_budget_minutes < 1:
        raise ValueError("The time budget must be at least 1 minute.")
    unknown = sorted(r for r in changed if r not in set(repository.record_ids("REQ")))
    if unknown:
        raise ValueError(f"Unknown changed requirement(s): {', '.join(unknown)}.")

    cases = repository.list_records("TC").records
    active = [case for case in cases if case.metadata["status"] == ACTIVE]
    covering: dict[str, list[str]] = {}
    for case in active:
        for requirement_id in case.metadata.get("requirements") or []:
            covering.setdefault(requirement_id, []).append(case.id)

    wanted: dict[str, list[Reason]] = {}
    related_ids: set[str] = set()
    for case in active:
        reasons: list[Reason] = []
        metadata = case.metadata
        mine = sorted(set(metadata.get("requirements") or []) & changed)
        if mine:
            related_ids.add(case.id)
            reasons.append(
                Reason("changed_requirements", f"covers changed {', '.join(mine)}")
            )
        if metadata.get("criticality") in HIGH_CRITICALITY or (
            metadata.get("priority") == "high"
        ):
            level = metadata.get("criticality") or "high priority"
            reasons.append(Reason("criticality", f"marked {level}"))
        sole = sorted(
            r
            for r in metadata.get("requirements") or []
            if covering.get(r) == [case.id] and r in changed
        )
        if sole:
            reasons.append(
                Reason("coverage", f"the only active case covering {', '.join(sole)}")
            )
        if metadata.get("type") in BASELINE_TYPES:
            reasons.append(
                Reason("regression_risk", f"a {metadata['type']} case guards the build")
            )
        if reasons:
            wanted[case.id] = reasons

    items: list[SelectionItem] = []
    used = 0
    ranked = sorted(
        (case for case in active if case.id in wanted),
        key=lambda case: _score(case, case.id in related_ids),
    )
    for case in ranked:
        estimate = case.metadata.get("estimated_minutes")
        reasons = list(wanted[case.id])
        if time_budget_minutes is not None and estimate is not None:
            if used + estimate > time_budget_minutes:
                items.append(
                    SelectionItem(
                        case.id,
                        "exclude",
                        (
                            Reason(
                                "time",
                                f"{estimate} min would exceed the {time_budget_minutes}"
                                f" min budget ({used} min already used)",
                            ),
                        ),
                    )
                )
                continue
            used += estimate
            reasons.append(Reason("time", f"{estimate} min, within the budget"))
        elif time_budget_minutes is not None:
            reasons.append(
                Reason("time", "no estimate, so it is not counted against the budget")
            )
        items.append(SelectionItem(case.id, "include", tuple(reasons)))

    decided = {item.id for item in items}
    for case in cases:
        if case.id in decided:
            continue
        status = case.metadata["status"]
        if status != ACTIVE:
            reason = Reason("readiness", f"the case is {status}, not active")
        else:
            reason = Reason(
                "changed_requirements",
                "not related to the changed requirements and not critical, "
                "unique coverage, or a baseline case",
            )
        items.append(SelectionItem(case.id, "exclude", (reason,)))
    items.sort(key=lambda item: item.id)
    return Recommendation(tuple(items), minutes_used=used)


@dataclass(frozen=True)
class PlanVerification:
    """Result of checking a plan's selection against the project's records.

    ``missing`` ids do not exist. ``not_ready`` are included cases that are not
    active. ``unverifiable`` ids are of a kind this repository does not store,
    so nothing is claimed about them.
    """

    missing: tuple[str, ...]
    not_ready: tuple[str, ...]
    unverifiable: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.not_ready


def verify_plan(repository: MarkdownRepository, plan_id: str) -> PlanVerification:
    """Check that everything a plan selects exists and is ready to run."""
    plan = repository.get(plan_id)
    selected = [
        (item["id"], item["decision"]) for item in plan.metadata.get("selection") or []
    ] + [(suite, "include") for suite in plan.metadata.get("suites") or []]
    missing: list[str] = []
    not_ready: list[str] = []
    unverifiable: list[str] = []
    for record_id, decision in selected:
        prefix = record_id.rsplit("-", 1)[0]
        if prefix not in repository.prefixes:
            unverifiable.append(record_id)
        elif record_id not in set(repository.record_ids(prefix)):
            missing.append(record_id)
        elif (
            prefix == "TC"
            and decision == "include"
            and repository.get(record_id).metadata["status"] != ACTIVE
        ):
            not_ready.append(record_id)
    return PlanVerification(
        tuple(sorted(set(missing))),
        tuple(sorted(set(not_ready))),
        tuple(sorted(set(unverifiable))),
    )
