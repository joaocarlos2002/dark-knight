"""Recording and reclassifying bug-hunting findings (spec 5.12)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from qa_workbench.bughunt.schema import CLASSIFICATIONS, SUSPECTED
from qa_workbench.core.secrets import find_secrets
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository, Record


class BugError(Exception):
    """A finding cannot be recorded or reclassified as asked."""


def _render(fields: dict[str, Any]) -> str:
    steps = "\n".join(f"{n}. {s}" for n, s in enumerate(fields.get("steps", []), 1))
    attempts = fields.get("attempts", 0)
    sections = [
        f"# {fields['title']}",
        f"**Classification:** {fields['status']}",
        f"**Environment:** {fields['environment']}",
        f"**Reproduced:** {fields.get('reproductions', 0)} of {attempts} attempts",
    ]
    if fields.get("context"):
        sections += ["## Context", fields["context"]]
    if steps:
        sections += ["## Steps to reproduce", steps]
    if fields.get("expected"):
        sections += ["## Expected result", fields["expected"]]
    if fields.get("observed"):
        sections += ["## Observed result", fields["observed"]]
    if fields.get("evidence"):
        sections += ["## Evidence", "\n".join(f"- {e}" for e in fields["evidence"])]
    if fields.get("impact"):
        sections += ["## Impact", fields["impact"]]
    if fields.get("limitations"):
        sections += ["## Limitations", fields["limitations"]]
    return "\n\n".join(sections) + "\n"


def _verify_evidence(repository: MarkdownRepository, evidence: Sequence[str]) -> None:
    store = EvidenceStore(repository)
    problems = []
    for evidence_id in evidence:
        try:
            problems += [f"{evidence_id}: {p}" for p in store.verify(evidence_id)]
        except StorageError as error:
            problems.append(f"{evidence_id}: {error}")
    if problems:
        listed = "\n".join(f"  - {p}" for p in problems)
        raise BugError(f"The evidence is not usable:\n{listed}")


def record_finding(
    repository: MarkdownRepository,
    *,
    title: str,
    environment: str,
    found_by: str,
    classification: str = SUSPECTED,
    steps: Sequence[str] = (),
    expected: str = "",
    observed: str = "",
    evidence: Sequence[str] = (),
    attempts: int = 1,
    reproductions: int = 0,
    context: str = "",
    impact: str = "",
    severity: str | None = None,
    reason: str = "",
    environment_issue: str = "",
    execution: str | None = None,
    requirements: Sequence[str] = (),
    limitations: str = "",
) -> Record:
    """Record a finding. A defect that is not proven stays a suspicion.

    Asking for ``reproduced`` without enough evidence is an error that lists
    what is missing; it is never quietly downgraded.
    """
    if classification not in CLASSIFICATIONS:
        raise BugError(
            f"classification must be one of {', '.join(CLASSIFICATIONS)}; "
            f"got {classification!r}."
        )
    fields: dict[str, Any] = {
        "status": classification,
        "title": title.strip(),
        "environment": environment.strip(),
        "found_by": found_by.strip(),
        "attempts": attempts,
        "reproductions": reproductions,
    }
    optional: dict[str, Any] = {
        "steps": [s.strip() for s in steps if s.strip()],
        "expected": expected.strip(),
        "observed": observed.strip(),
        "evidence": list(evidence),
        "context": context.strip(),
        "impact": impact.strip(),
        "severity": severity,
        "reason": reason.strip(),
        "environment_issue": environment_issue.strip(),
        "execution": execution,
        "requirements": list(requirements),
        "limitations": limitations.strip(),
    }
    fields.update({k: v for k, v in optional.items() if v})
    leaks = {leak for text in _texts(fields) for leak in find_secrets(text)}
    if leaks:
        raise BugError(
            f"The finding contains {', '.join(sorted(leaks))}; reference it by name "
            "instead of writing the value."
        )
    if evidence:
        _verify_evidence(repository, evidence)
    try:
        return repository.create("BUG", fields, _render(fields))
    except StorageError as error:
        raise BugError(str(error)) from error


def _texts(fields: dict[str, Any]) -> list[str]:
    texts = [
        str(fields.get(n, "")) for n in ("title", "expected", "observed", "context")
    ]
    return texts + [str(s) for s in fields.get("steps", [])]


def reclassify(
    repository: MarkdownRepository,
    bug_id: str,
    classification: str,
    *,
    by: str,
    justification: str,
    attempts: int | None = None,
    reproductions: int | None = None,
    reason: str = "",
) -> Record:
    """Change a classification, keeping who changed it, when, and why."""
    if classification not in CLASSIFICATIONS:
        raise BugError(f"classification must be one of {', '.join(CLASSIFICATIONS)}.")
    if not by.strip() or not justification.strip():
        raise BugError("Reclassifying needs who is doing it and a justification.")
    current = repository.get(bug_id)
    history = list(current.metadata.get("classification_history", []))
    history.append(
        {
            "from": current.metadata["status"],
            "to": classification,
            "by": by.strip(),
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "why": justification.strip(),
        }
    )
    changes: dict[str, Any] = {
        "status": classification,
        "classification_history": history,
    }
    if attempts is not None:
        changes["attempts"] = attempts
    if reproductions is not None:
        changes["reproductions"] = reproductions
    if reason.strip():
        changes["reason"] = reason.strip()
    merged = {**current.metadata, **changes}
    try:
        return repository.update(bug_id, changes, _render(merged))
    except StorageError as error:
        raise BugError(str(error)) from error
