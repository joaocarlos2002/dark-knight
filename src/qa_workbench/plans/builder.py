"""Create and update test plan records."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from qa_workbench.plans.schema import DRAFT, INCLUDE
from qa_workbench.storage.repository import MarkdownRepository, Record


@dataclass
class Risk:
    description: str
    level: str
    mitigation: str = ""


@dataclass
class PlanDraft:
    """Everything the author provides for a new test plan.

    Validation happens when the record is written.
    """

    __test__ = False  # not a pytest test class

    title: str
    scope: str
    strategy: str
    objectives: list[str] = field(default_factory=list)
    entry_criteria: list[str] = field(default_factory=list)
    exit_criteria: list[str] = field(default_factory=list)
    in_scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    levels: list[str] = field(default_factory=list)
    test_types: list[str] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    profiles: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    suites: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    schedule_start: datetime | None = None
    schedule_end: datetime | None = None
    origin: str = "manual"
    generated_by: str | None = None

    def to_fields(self, status: str = DRAFT) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "title": self.title.strip(),
            "status": status,
            "origin": self.origin,
            "scope": self.scope.strip(),
            "strategy": self.strategy.strip(),
            "objectives": self.objectives,
            "entry_criteria": self.entry_criteria,
            "exit_criteria": self.exit_criteria,
        }
        optional: dict[str, Any] = {
            "in_scope": self.in_scope,
            "out_of_scope": self.out_of_scope,
            "levels": self.levels,
            "test_types": self.test_types,
            "environments": self.environments,
            "profiles": self.profiles,
            "data": self.data,
            "dependencies": self.dependencies,
            "risks": [
                {
                    "description": r.description,
                    "level": r.level,
                    "mitigation": r.mitigation,
                }
                if r.mitigation
                else {"description": r.description, "level": r.level}
                for r in self.risks
            ],
            "suites": self.suites,
            "owners": self.owners,
            "generated_by": self.generated_by.strip() if self.generated_by else None,
        }
        fields.update({key: value for key, value in optional.items() if value})
        if self.schedule_start is not None or self.schedule_end is not None:
            fields["schedule"] = {
                key: value
                for key, value in (
                    ("start", self.schedule_start),
                    ("end", self.schedule_end),
                )
                if value is not None
            }
        return fields


def _bullets(parts: list[str], heading: str, items: Any) -> None:
    if isinstance(items, list) and items:
        parts.append(f"## {heading}\n\n" + "\n".join(f"- {item}" for item in items))


def render_body(metadata: Mapping[str, Any]) -> str:
    """The human-readable Markdown of a plan, built from its fields.

    It runs before validation, so it skips what it cannot read.
    """
    parts = [f"# {metadata.get('title', '')}"]
    parts.append(f"## Scope\n\n{metadata.get('scope', '')}")
    _bullets(parts, "In scope", metadata.get("in_scope"))
    _bullets(parts, "Out of scope", metadata.get("out_of_scope"))
    _bullets(parts, "Objectives", metadata.get("objectives"))
    parts.append(f"## Strategy\n\n{metadata.get('strategy', '')}")
    _bullets(parts, "Test levels", metadata.get("levels"))
    _bullets(parts, "Test types", metadata.get("test_types"))
    _bullets(parts, "Environments", metadata.get("environments"))
    _bullets(parts, "Profiles", metadata.get("profiles"))
    _bullets(parts, "Test data", metadata.get("data"))
    _bullets(parts, "Dependencies", metadata.get("dependencies"))
    risks = metadata.get("risks")
    if isinstance(risks, list) and risks:
        lines = []
        for risk in risks:
            if isinstance(risk, dict):
                line = f"- [{risk.get('level', '?')}] {risk.get('description', '')}"
                if risk.get("mitigation"):
                    line += f" Mitigation: {risk['mitigation']}"
                lines.append(line)
        parts.append("## Risks\n\n" + "\n".join(lines))
    _bullets(parts, "Entry criteria", metadata.get("entry_criteria"))
    _bullets(parts, "Exit criteria", metadata.get("exit_criteria"))
    _bullets(parts, "Suites", metadata.get("suites"))
    _bullets(parts, "Owners", metadata.get("owners"))
    schedule = metadata.get("schedule")
    if isinstance(schedule, dict):
        start = schedule.get("start")
        end = schedule.get("end")
        parts.append(
            "## Schedule\n\n"
            f"- Start: {start.isoformat() if hasattr(start, 'isoformat') else start}\n"
            f"- End: {end.isoformat() if hasattr(end, 'isoformat') else end}"
        )
    selection = metadata.get("selection")
    if isinstance(selection, list) and selection:
        lines = []
        for item in selection:
            if not isinstance(item, dict):
                continue
            verb = "Include" if item.get("decision") == INCLUDE else "Exclude"
            lines.append(f"### {verb} {item.get('id', '?')}")
            for reason in item.get("reasons") or []:
                if isinstance(reason, dict):
                    lines.append(
                        f"- {reason.get('factor', '?')}: {reason.get('detail', '')}"
                    )
            lines.append("")
        parts.append("## Selection and rationale\n\n" + "\n".join(lines).rstrip())
    return "\n\n".join(parts) + "\n"


def create_plan(
    repository: MarkdownRepository, draft: PlanDraft, *, status: str = DRAFT
) -> Record:
    """Write a new test plan. Problems raise ``RecordValidationError``."""
    fields = draft.to_fields(status)
    return repository.create("TP", fields, render_body(fields))


def update_plan(
    repository: MarkdownRepository, plan_id: str, changes: Mapping[str, Any]
) -> Record:
    """Change fields of a plan and rebuild its readable body."""
    current = repository.get(plan_id)
    merged = {**current.metadata, **changes}
    return repository.update(plan_id, changes, render_body(merged))


def set_selection(
    repository: MarkdownRepository, plan_id: str, selection: list[dict[str, Any]]
) -> Record:
    """Store a selection, with its reasons, on a plan."""
    return update_plan(repository, plan_id, {"selection": selection})
