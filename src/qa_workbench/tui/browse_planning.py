"""Rows and detail text for suites and test plans (pure, no widgets)."""

from datetime import datetime
from typing import Any

from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.tui.browse import BrowseData, BrowseRow, as_list, section
from qa_workbench.tui.data import effective_status

SUITE_COLUMNS = ("ID", "Type", "Status", "Cases", "Title")
PLAN_COLUMNS = ("ID", "Status", "Suites", "Selected", "Title")


def _case_line(repository: MarkdownRepository, case_id: str) -> tuple[str, int | None]:
    """A case as ``TC-001  Title [status]`` and its estimate in minutes, if any."""
    try:
        meta = repository.get(case_id).metadata
    except StorageError:
        return f"{case_id}  (record not found)", None
    estimate = meta.get("estimated_minutes")
    return (
        f"{case_id}  {meta.get('title', '')} [{meta.get('status', '?')}]",
        estimate if isinstance(estimate, int) else None,
    )


def _estimate(minutes: list[int | None]) -> str:
    known = [m for m in minutes if m is not None]
    if not minutes or not known:
        return "no estimates recorded"
    total = sum(known)
    if len(known) == len(minutes):
        return f"{total} min"
    return f"{total} min (only {len(known)} of {len(minutes)} cases have an estimate)"


def _last_execution(repository: MarkdownRepository, cases: set[str], suite: str) -> str:
    if "EXEC" not in repository.prefixes:
        return "none recorded"
    latest: Record | None = None
    for record in repository.list_records("EXEC").records:
        related = record.metadata.get("suite") == suite or (
            record.metadata.get("test_case") in cases
        )
        if related and (latest is None or _stamp(record) > _stamp(latest)):
            latest = record
    if latest is None:
        return "none recorded"
    return f"{latest.id} ({effective_status(latest.metadata)})"


def _stamp(record: Record) -> str:
    value = record.metadata.get("updated_at")
    return value.isoformat() if isinstance(value, datetime) else ""


# -- suites ---------------------------------------------------------------------


def suite_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("SUITE")
    rows = []
    for record in listing.records:
        meta = record.metadata
        cases = as_list(meta.get("cases"))
        status, kind, title = str(meta["status"]), str(meta["type"]), str(meta["title"])
        tags = " ".join(as_list(meta.get("tags")))
        rows.append(
            BrowseRow(
                record.id,
                (record.id, kind, status, str(len(cases)), title),
                status,
                f"{record.id} {title} {kind} {status} {tags}".lower(),
            )
        )
    return BrowseData(tuple(rows), tuple(f"SUITE: {e}" for e in listing.errors))


def suite_detail(repository: MarkdownRepository, suite_id: str) -> str:
    record = repository.get(suite_id)
    meta = record.metadata
    cases = as_list(meta.get("cases"))
    described = [_case_line(repository, c) for c in cases]
    lines = [
        f"{record.id}  {meta['title']}",
        f"Type {meta['type']}   Status {meta['status']}   Tags "
        f"{', '.join(as_list(meta.get('tags'))) or '-'}",
        str(meta.get("description") or "(no description)"),
    ]
    lines += section("TEST CASES", [line for line, _ in described], "no cases yet")
    estimate = _estimate([m for _, m in described])
    lines += [
        "",
        f"Total: {len(cases)} case(s)   Estimate: {estimate}",
        f"Last execution: {_last_execution(repository, set(cases), suite_id)}",
    ]
    missing = [
        c for c, (line, _) in zip(cases, described, strict=True) if "not found" in line
    ]
    if missing:
        lines += ["", f"WARNING: {', '.join(missing)} named here but missing."]
    return "\n".join(lines)


# -- plans ------------------------------------------------------------------------


def _selection(meta: dict[str, Any]) -> list[dict[str, Any]]:
    items = meta.get("selection")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def plan_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("TP")
    rows = []
    for record in listing.records:
        meta = record.metadata
        status, title = str(meta["status"]), str(meta["title"])
        included = sum(1 for i in _selection(meta) if i.get("decision") == "include")
        rows.append(
            BrowseRow(
                record.id,
                (
                    record.id,
                    status,
                    str(len(as_list(meta.get("suites")))),
                    str(included),
                    title,
                ),
                status,
                f"{record.id} {title} {status}".lower(),
            )
        )
    return BrowseData(tuple(rows), tuple(f"TP: {e}" for e in listing.errors))


def plan_detail(repository: MarkdownRepository, plan_id: str) -> str:
    record = repository.get(plan_id)
    meta = record.metadata
    lines = [
        f"{record.id}  {meta['title']}",
        f"Status {meta['status']}   Origin {meta['origin']}   Owners "
        f"{', '.join(as_list(meta.get('owners'))) or '-'}",
        "",
        "SCOPE",
        f"  {meta.get('scope') or '(none)'}",
    ]
    for label, key in (("Included", "in_scope"), ("Excluded", "out_of_scope")):
        if meta.get(key):
            lines.append(f"  {label}: {', '.join(as_list(meta[key]))}")
    lines += ["", "STRATEGY", f"  {meta.get('strategy') or '(none)'}"]
    lines += section("OBJECTIVES", as_list(meta.get("objectives")))
    lines += section("ENTRY CRITERIA", as_list(meta.get("entry_criteria")))
    lines += section("EXIT CRITERIA", as_list(meta.get("exit_criteria")))

    suite_lines = []
    for suite_id in as_list(meta.get("suites")):
        try:
            suite = repository.get(suite_id)
            count = len(as_list(suite.metadata.get("cases")))
            suite_lines.append(f"{suite_id}  {suite.metadata['title']} ({count} cases)")
        except StorageError:
            suite_lines.append(f"{suite_id}  (record not found)")
    lines += section("SELECTED SUITES", suite_lines, "no suites")

    selection = _selection(meta)
    included = [i for i in selection if i.get("decision") == "include"]
    excluded = [i for i in selection if i.get("decision") == "exclude"]
    estimates = [_case_line(repository, str(i.get("id")))[1] for i in included]
    lines += [
        "",
        "SELECTION",
        f"  {len(included)} included, {len(excluded)} excluded"
        f"   Estimate: {_estimate(estimates)}"
        if selection
        else "  (no selection yet: use `batman plans recommend`)",
    ]
    for item in included[:10]:
        reasons = "; ".join(
            str(r.get("detail", ""))
            for r in item.get("reasons", [])
            if isinstance(r, dict)
        )
        lines.append(f"  + {item.get('id')}  {reasons or '(no reason recorded)'}")
    risks = [r for r in (meta.get("risks") or []) if isinstance(r, dict)]
    if risks:
        lines += section(
            "RISKS", [f"[{r.get('level')}] {r.get('description')}" for r in risks]
        )
    return "\n".join(lines)
