"""Reusable suites and many-to-many membership (REQ-015).

A test case can belong to any number of suites, and a suite holds any number of
cases. The suite's ``cases`` list is where the workbench writes membership. A
case may also name its suites in ``suites`` (for example when edited by hand in
Obsidian); membership is the union of both sides, so neither can contradict the
other.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.suites.schema import DRAFT

ACTIVE = "active"


class SuiteError(Exception):
    """Raised when a membership change is not allowed."""


@dataclass(frozen=True)
class Membership:
    """Which cases are in which suites, from both sides, existing records only."""

    suite_cases: Mapping[str, tuple[str, ...]]
    case_suites: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class SuiteSummary:
    id: str
    title: str
    type: str
    status: str
    cases: tuple[str, ...]


@dataclass(frozen=True)
class SuiteCheck:
    """Problems with a suite's members.

    ``missing`` cases do not exist. ``not_active`` cases exist but are not
    approved yet, which a suite under construction may legitimately contain.
    """

    missing: tuple[str, ...]
    not_active: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing


def _titles(repository: MarkdownRepository) -> dict[str, str]:
    if "TC" not in repository.prefixes:
        return {}
    return {
        record.id: str(record.metadata.get("title", ""))
        for record in repository.list_records("TC").records
    }


def render_body(metadata: Mapping[str, Any], titles: Mapping[str, str]) -> str:
    """Readable Markdown for a suite; cases are Obsidian links."""
    parts = [f"# {metadata.get('title', '')}"]
    if metadata.get("description"):
        parts.append(str(metadata["description"]))
    cases = metadata.get("cases")
    if isinstance(cases, list) and cases:
        lines = [
            f"- [[{case_id}]] {titles.get(str(case_id), '(missing)')}"
            for case_id in cases
        ]
        parts.append("## Cases\n\n" + "\n".join(lines))
    return "\n\n".join(parts) + "\n"


def _existing_cases(repository: MarkdownRepository) -> set[str]:
    return set(repository.record_ids("TC")) if "TC" in repository.prefixes else set()


def create_suite(
    repository: MarkdownRepository,
    title: str,
    suite_type: str,
    *,
    description: str = "",
    cases: Sequence[str] = (),
    tags: Sequence[str] = (),
    status: str = DRAFT,
) -> Record:
    """Create a suite, optionally with its first cases."""
    _require_existing(repository, cases)
    fields: dict[str, Any] = {
        "title": title.strip(),
        "status": status,
        "type": suite_type,
    }
    optional = {
        "description": description.strip(),
        "cases": list(cases),
        "tags": list(tags),
    }
    fields.update({key: value for key, value in optional.items() if value})
    return repository.create("SUITE", fields, render_body(fields, _titles(repository)))


def _require_existing(repository: MarkdownRepository, case_ids: Iterable[str]) -> None:
    existing = _existing_cases(repository)
    missing = sorted(
        c for c in case_ids if "TC" in repository.prefixes and c not in existing
    )
    if missing:
        raise SuiteError(f"These test cases do not exist: {', '.join(missing)}.")


def add_cases(
    repository: MarkdownRepository, suite_id: str, case_ids: Sequence[str]
) -> Record:
    """Add cases to a suite. Cases may already belong to other suites."""
    suite = repository.get(suite_id)
    current = list(suite.metadata.get("cases") or [])
    already = sorted({c for c in case_ids if c in current})
    if already:
        raise SuiteError(f"{suite_id} already contains: {', '.join(already)}.")
    if len(set(case_ids)) != len(case_ids):
        raise SuiteError("The same case was given more than once.")
    _require_existing(repository, case_ids)
    return _save(repository, suite, [*current, *case_ids])


def remove_cases(
    repository: MarkdownRepository, suite_id: str, case_ids: Sequence[str]
) -> Record:
    """Remove cases from a suite. The cases themselves are untouched."""
    suite = repository.get(suite_id)
    current = list(suite.metadata.get("cases") or [])
    absent = sorted({c for c in case_ids if c not in current})
    if absent:
        raise SuiteError(f"{suite_id} does not contain: {', '.join(absent)}.")
    remaining = [c for c in current if c not in set(case_ids)]
    return _save(repository, suite, remaining)


def _save(repository: MarkdownRepository, suite: Record, cases: list[str]) -> Record:
    body = render_body({**suite.metadata, "cases": cases}, _titles(repository))
    return repository.update(suite.id, {"cases": cases}, body)


def membership(repository: MarkdownRepository) -> Membership:
    """Suite and case membership, from both sides, for records that exist."""
    existing = _existing_cases(repository)
    suites = repository.list_records("SUITE").records
    suite_ids = {suite.id for suite in suites}
    by_suite: dict[str, set[str]] = {suite.id: set() for suite in suites}
    for suite in suites:
        by_suite[suite.id].update(
            c for c in suite.metadata.get("cases") or [] if c in existing
        )
    if "TC" in repository.prefixes:
        for case in repository.list_records("TC").records:
            for suite_id in case.metadata.get("suites") or []:
                if suite_id in suite_ids:
                    by_suite[suite_id].add(case.id)
    by_case: dict[str, set[str]] = {}
    for suite_id, cases in by_suite.items():
        for case_id in cases:
            by_case.setdefault(case_id, set()).add(suite_id)
    return Membership(
        {s: tuple(sorted(c)) for s, c in sorted(by_suite.items())},
        {c: tuple(sorted(s)) for c, s in sorted(by_case.items())},
    )


def summarize(repository: MarkdownRepository) -> list[SuiteSummary]:
    """Every suite with its effective members, ordered by id."""
    members = membership(repository)
    return [
        SuiteSummary(
            id=suite.id,
            title=suite.metadata["title"],
            type=suite.metadata["type"],
            status=suite.metadata["status"],
            cases=members.suite_cases.get(suite.id, ()),
        )
        for suite in repository.list_records("SUITE").records
    ]


def verify_suite(repository: MarkdownRepository, suite_id: str) -> SuiteCheck:
    """Check that the cases a suite names exist, and which are not active yet."""
    suite = repository.get(suite_id)
    declared = list(suite.metadata.get("cases") or [])
    if "TC" not in repository.prefixes:
        return SuiteCheck((), ())
    existing = _existing_cases(repository)
    missing = sorted(c for c in declared if c not in existing)
    not_active = sorted(
        c
        for c in declared
        if c in existing and repository.get(c).metadata["status"] != ACTIVE
    )
    return SuiteCheck(tuple(missing), tuple(not_active))
