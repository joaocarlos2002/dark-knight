"""Rows and detail text for reports and evidence (pure, no widgets)."""

from pathlib import Path
from typing import Any

from qa_workbench.reports.writer import (
    REPORTS_DIRECTORY,
    is_execution_report_stale,
    report_path,
)
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.tui.browse import BrowseData, BrowseRow

REPORT_COLUMNS = ("ID", "Type", "Status", "Source", "Title")
EVIDENCE_COLUMNS = ("ID", "Status", "Source", "Size", "Description")


def _row(
    record: Record, cells: tuple[str, ...], status: str, extra: str = ""
) -> BrowseRow:
    return BrowseRow(record.id, cells, status, f"{' '.join(cells)} {extra}".lower())


def _with_body(header: list[str], record: Record) -> str:
    return "\n".join([*header, "", record.body.strip()])


def _list_report_files(repository: MarkdownRepository) -> list[Path]:
    """List all saved report files in the project's reports directory."""
    reports_dir = repository.root / REPORTS_DIRECTORY
    if not reports_dir.is_dir():
        return []
    return sorted(
        reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
    )


def _parse_report_metadata(path: Path) -> dict[str, Any] | None:
    """Read a report file and return its frontmatter metadata."""
    try:
        from qa_workbench.storage.frontmatter import read_document

        doc = read_document(path)
        return doc.metadata
    except Exception:
        return None


def report_rows(repository: MarkdownRepository) -> BrowseData:
    """List all saved reports in the project."""
    rows = []
    problems: list[str] = []
    files = _list_report_files(repository)

    for path in files:
        meta = _parse_report_metadata(path)
        if meta is None:
            problems.append(f"report {path.name}: cannot read frontmatter")
            continue

        report_type = str(meta.get("report", "unknown"))
        source = str(meta.get("source", "-"))
        status = str(meta.get("execution_status", "saved"))
        title = path.stem

        stale = is_execution_report_stale(repository, source)
        if stale is True:
            status += " (stale)"
        elif stale is None:
            pass  # not an execution report

        cells = (title, report_type, status, source, title)
        rows.append(
            BrowseRow(
                path.stem,
                cells,
                status,
                f"{title} {report_type} {status} {source}".lower(),
            )
        )

    return BrowseData(tuple(rows), tuple(problems))


def report_detail(repository: MarkdownRepository, report_id: str) -> str:
    """Show the full content of a saved report."""
    path = report_path(repository, report_id)
    if not path.is_file():
        return f"Report {report_id} not found."

    try:
        from qa_workbench.storage.frontmatter import read_document

        doc = read_document(path)
    except Exception as error:
        return f"Report {report_id} could not be read: {error}"

    meta = doc.metadata
    lines = [
        f"{report_id}  ({meta.get('report', 'unknown')})",
        f"Source execution: {meta.get('source', '-')}",
        f"Generated at: {meta.get('generated_at', '-')}",
        f"Status: {meta.get('execution_status', '-')}",
    ]
    stale = is_execution_report_stale(repository, str(meta.get("source", "")))
    if stale is True:
        lines.append(
            "STATUS: STALE — the source execution has changed "
            "since this report was saved."
        )
    elif stale is False:
        lines.append("Status: current (matches the source execution).")
    lines += ["", doc.body.strip()]
    return "\n".join(lines)


def evidence_rows(repository: MarkdownRepository) -> BrowseData:
    """List all evidence records in the project."""
    if "EVD" not in repository.prefixes:
        return BrowseData((), ("EVD schema not registered in this project.",))

    store = EvidenceStore(repository)
    listing = store.list_records()
    rows = []
    for record in listing.records:
        meta = record.metadata
        problems = store.verify(record.id)
        is_intact = len(problems) == 0
        status = "intact" if is_intact else "tampered"
        cells = (
            record.id,
            status,
            str(meta.get("source", "-")),
            str(meta.get("size", 0)),
            str(meta.get("description", ""))[:80],
        )
        rows.append(
            BrowseRow(
                record.id,
                cells,
                status,
                " ".join(
                    [
                        record.id,
                        status,
                        str(meta.get("source", "")),
                        str(meta.get("description", "")),
                    ]
                ).lower(),
            )
        )
    problems = tuple(f"EVD: {e}" for e in listing.errors)
    return BrowseData(tuple(rows), problems)


def evidence_detail(repository: MarkdownRepository, evidence_id: str) -> str:
    """Show the full detail of an evidence record with verification."""
    if "EVD" not in repository.prefixes:
        return "Evidence records are not available in this project."

    store = EvidenceStore(repository)
    try:
        record = store.get(evidence_id)
    except Exception as error:
        return f"Evidence {evidence_id} could not be read: {error}"

    meta = record.metadata
    problems = store.verify(evidence_id)
    is_intact = len(problems) == 0

    lines = [
        f"{evidence_id}  {'INTEGRITY VERIFIED' if is_intact else 'INTEGRITY PROBLEM'}",
        f"File: {meta.get('file', '-')}",
        f"Original name: {meta.get('original_name', '-')}",
        f"SHA-256: {meta.get('sha256', '-')}",
        f"Size: {meta.get('size', 0)} bytes",
        f"Media type: {meta.get('media_type', '-')}",
        f"Source: {meta.get('source', '-')}",
        f"Description: {meta.get('description', '-')}",
    ]
    if meta.get("execution"):
        lines.append(f"Execution: {meta['execution']}")
    if meta.get("step"):
        lines.append(f"Step: {meta['step']}")
    if meta.get("source_url"):
        lines.append(f"Source URL: {meta['source_url']}")
    if meta.get("derived_from"):
        lines.append(f"Derived from: {meta['derived_from']}")
    if meta.get("captured_at"):
        lines.append(f"Captured at: {meta['captured_at']}")

    if problems:
        lines += ["", "INTEGRITY PROBLEMS:", *[f"  - {p}" for p in problems]]
    else:
        lines += ["", "No integrity problems found."]

    return "\n".join(lines)
