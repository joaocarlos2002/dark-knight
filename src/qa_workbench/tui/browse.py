"""Rows and detail text for list + detail pages (pure, no widgets).

A :class:`BrowseRow` is what the list shows and what the search matches. The
detail text is built only from the record's own fields, and anything missing is
said to be missing rather than filled in.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from qa_workbench.requirements.coverage import coverage
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository

ALL = "all"


@dataclass(frozen=True)
class BrowseRow:
    key: str
    cells: tuple[str, ...]
    status: str
    search: str


@dataclass(frozen=True)
class BrowseData:
    rows: tuple[BrowseRow, ...]
    problems: tuple[str, ...] = ()


def filter_rows(rows: Sequence[BrowseRow], query: str, status: str) -> list[BrowseRow]:
    """Rows that match every word of ``query`` (any case) and the status filter."""
    words = query.lower().split()
    return [
        row
        for row in rows
        if (status == ALL or row.status == status)
        and all(word in row.search for word in words)
    ]


def _list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _lines(title: str, items: Sequence[str], empty: str = "none") -> list[str]:
    return ["", title, *([f"  - {item}" for item in items] or [f"  ({empty})"])]


def _titles(repository: MarkdownRepository, ids: Sequence[str]) -> list[str]:
    found = []
    for record_id in ids:
        try:
            title = str(repository.get(record_id).metadata.get("title", ""))
            found.append(f"{record_id}  {title}".rstrip())
        except StorageError:
            found.append(f"{record_id}  (record not found)")
    return found


# -- requirements ---------------------------------------------------------------

REQUIREMENT_COLUMNS = ("ID", "Priority", "Status", "Cases", "Title")


def requirement_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("REQ")
    problems = tuple(f"REQ: {error}" for error in listing.errors)
    by_id = {c.id: c for c in coverage(repository)} if listing.records else {}
    rows = []
    for record in listing.records:
        meta = record.metadata
        covered = by_id[record.id].cases if record.id in by_id else ()
        status = str(meta["status"])
        priority = str(meta.get("priority") or "-")
        title = str(meta["title"])
        tags = " ".join(_list(meta.get("tags")))
        rows.append(
            BrowseRow(
                record.id,
                (
                    record.id,
                    priority,
                    status,
                    f"{len(covered)} case(s)" if covered else "NOT COVERED",
                    title,
                ),
                status,
                f"{record.id} {title} {status} {priority} {tags}".lower(),
            )
        )
    return BrowseData(tuple(rows), problems)


def requirement_detail(repository: MarkdownRepository, record_id: str) -> str:
    record = repository.get(record_id)
    meta = record.metadata
    report = {c.id: c for c in coverage(repository)}.get(record_id)
    cases = list(report.cases) if report else []
    source = f"Source {meta['source']}"
    if meta.get("source_ref"):
        source += f" ({meta['source_ref']})"
    tags = ", ".join(_list(meta.get("tags"))) or "-"
    lines = [
        f"{record.id}  {meta['title']}",
        f"Status {meta['status']}   Priority {meta.get('priority') or '-'}   "
        f"Origin {meta['origin']}",
        source,
        f"Author {meta.get('author') or '-'}   Tags {tags}",
    ]
    lines += _lines("ACCEPTANCE CRITERIA", _list(meta.get("acceptance_criteria")))
    lines += _lines(
        "RELATED TEST CASES", _titles(repository, cases), "no test case covers this"
    )
    if report and report.missing_cases:
        lines += _lines("NAMED BUT MISSING", list(report.missing_cases))
    reviews = meta.get("reviews")
    if isinstance(reviews, list) and reviews:
        lines += _lines(
            "REVIEWS",
            [
                f"{r.get('decision')} by {r.get('reviewer')} on {r.get('at', '-')}"
                for r in reviews
                if isinstance(r, dict)
            ],
        )
    # The criteria are shown above, so the body's own copy of them is dropped.
    description = record.body.split("## Acceptance criteria")[0].strip()
    lines += ["", description]
    return "\n".join(lines)


# -- test cases -------------------------------------------------------------------

CASE_COLUMNS = ("ID", "Priority", "Status", "Type", "Title")


def case_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("TC")
    rows = []
    for record in listing.records:
        meta = record.metadata
        status = str(meta["status"])
        title = str(meta["title"])
        tags = " ".join(_list(meta.get("tags")))
        requirements = " ".join(_list(meta.get("requirements")))
        rows.append(
            BrowseRow(
                record.id,
                (record.id, str(meta["priority"]), status, str(meta["type"]), title),
                status,
                f"{record.id} {title} {status} {meta['priority']} {meta['type']} "
                f"{tags} {requirements}".lower(),
            )
        )
    return BrowseData(tuple(rows), tuple(f"TC: {e}" for e in listing.errors))


def case_detail(repository: MarkdownRepository, record_id: str) -> str:
    record = repository.get(record_id)
    meta = record.metadata
    steps = []
    for number, step in enumerate(meta.get("steps") or [], start=1):
        if isinstance(step, dict):
            text = str(step.get("action", ""))
            if step.get("expected"):
                text += f"  =>  {step['expected']}"
            steps.append(f"{number}. {text}")
    lines = [
        f"{record.id}  {meta['title']}",
        f"Status {meta['status']}   Priority {meta['priority']}   "
        f"Type {meta['type']}   Origin {meta['origin']}",
        f"Objective: {meta['objective']}",
        "Requirements: " + (", ".join(_list(meta.get("requirements"))) or "-"),
        "Suites: " + (", ".join(_list(meta.get("suites"))) or "-"),
        "Tags: " + (", ".join(_list(meta.get("tags"))) or "-"),
    ]
    lines += _lines("PRECONDITIONS", _list(meta.get("preconditions")))
    lines += ["", "STEPS", *(f"  {s}" for s in steps or ["  (no steps)"])]
    lines += ["", "EXPECTED RESULT", f"  {meta.get('expected_result') or '(none)'}"]
    if meta.get("test_data"):
        lines += _lines("TEST DATA", _list(meta["test_data"]))
    return "\n".join(lines)
