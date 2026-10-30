"""Create and update test case records."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.testcases.schema import DRAFT
from qa_workbench.testcases.techniques import parse_technique


@dataclass
class Step:
    """One step and, when it applies, what must be observed after it."""

    action: str
    expected: str = ""


@dataclass
class TestCaseDraft:
    """Everything the author provides for a new test case.

    Validation happens when the record is written, with the same rules used
    when a file is read back, so a draft cannot create a record that would later
    be rejected.
    """

    __test__ = False  # not a pytest test class

    title: str
    objective: str
    steps: list[Step] = field(default_factory=list)
    expected_result: str = ""
    preconditions: list[str] = field(default_factory=list)
    test_data: list[str] = field(default_factory=list)
    priority: str = "medium"
    criticality: str | None = None
    type: str = "functional"
    profile: str = ""
    environments: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suites: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    technique_data: dict[str, Any] = field(default_factory=dict)
    origin: str = "manual"
    author: str | None = None

    def to_fields(self, status: str = DRAFT) -> dict[str, Any]:
        """Frontmatter fields; empty optional values are left out."""
        fields: dict[str, Any] = {
            "title": self.title.strip(),
            "status": status,
            "priority": self.priority,
            "type": self.type,
            "origin": self.origin,
            "objective": self.objective.strip(),
            "steps": [
                {"action": step.action, "expected": step.expected}
                if step.expected
                else {"action": step.action}
                for step in self.steps
            ],
        }
        optional: dict[str, Any] = {
            "expected_result": self.expected_result.strip(),
            "criticality": self.criticality,
            "profile": self.profile.strip(),
            "author": self.author.strip() if self.author else None,
            "preconditions": self.preconditions,
            "test_data": self.test_data,
            "environments": self.environments,
            "requirements": self.requirements,
            "issues": self.issues,
            "suites": self.suites,
            "tags": self.tags,
            "techniques": self.techniques,
            "technique_data": self.technique_data,
        }
        fields.update({key: value for key, value in optional.items() if value})
        return fields


def render_body(metadata: Mapping[str, Any]) -> str:
    """The human-readable Markdown of a test case, built from its fields.

    It runs before validation, so it skips what it cannot read; the validation
    reports those problems.
    """
    parts = [f"# {metadata.get('title', '')}"]
    parts.append(f"## Objective\n\n{metadata.get('objective', '')}")

    def bullets(heading: str, key: str) -> None:
        items = metadata.get(key) or []
        if isinstance(items, list) and items:
            listed = "\n".join(f"- {item}" for item in items)
            parts.append(f"## {heading}\n\n{listed}")

    bullets("Preconditions", "preconditions")
    bullets("Test data", "test_data")
    steps = metadata.get("steps") or []
    if isinstance(steps, list) and steps:
        lines: list[str] = []
        for number, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            lines.append(f"{number}. {step.get('action', '')}")
            if step.get("expected"):
                lines.append(f"   - Expected: {step['expected']}")
        parts.append("## Steps\n\n" + "\n".join(lines))
    if metadata.get("expected_result"):
        parts.append(f"## Expected result\n\n{metadata['expected_result']}")
    technique_data = metadata.get("technique_data")
    if not isinstance(technique_data, dict):
        technique_data = {}
    for name, data in technique_data.items():
        try:
            conditions = parse_technique(name, data).derive()  # type: ignore[attr-defined]
        except ValueError:
            continue
        if conditions:
            listed = "\n".join(
                f"- {c.label}: {c.value}" + ("" if c.valid else " (invalid)")
                for c in conditions
            )
            parts.append(f"## Technique: {name.replace('_', ' ')}\n\n{listed}")
    return "\n\n".join(parts) + "\n"


def create_test_case(
    repository: MarkdownRepository, draft: TestCaseDraft, *, status: str = DRAFT
) -> Record:
    """Write a new test case. Problems raise ``RecordValidationError``."""
    fields = draft.to_fields(status)
    return repository.create("TC", fields, render_body(fields))


def update_test_case(
    repository: MarkdownRepository, record_id: str, changes: Mapping[str, Any]
) -> Record:
    """Change fields of a test case and rebuild its readable body."""
    current = repository.get(record_id)
    merged = {**current.metadata, **changes}
    return repository.update(record_id, changes, render_body(merged))
