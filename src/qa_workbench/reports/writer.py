"""Write reports to ``<project>/reports`` and tell when one is out of date."""

from datetime import datetime
from pathlib import Path

from qa_workbench.reports.execution import render_execution_report, source_hash
from qa_workbench.reports.traceability import build_graph, matrix
from qa_workbench.storage.atomic import write_text_atomic
from qa_workbench.storage.errors import FrontmatterError
from qa_workbench.storage.frontmatter import dump_document, read_document
from qa_workbench.storage.repository import MarkdownRepository

REPORTS_DIRECTORY = "reports"


def _now() -> datetime:
    return datetime.now().astimezone()


def report_path(repository: MarkdownRepository, name: str) -> Path:
    return repository.root / REPORTS_DIRECTORY / f"{name}.md"


def write_execution_report(repository: MarkdownRepository, execution_id: str) -> Path:
    """Generate and save the report of an execution.

    The file records the SHA-256 of the execution it describes, so a later
    change (a correction, for example) shows up as a stale report.
    """
    body = render_execution_report(repository, execution_id)
    metadata = {
        "report": "execution",
        "source": execution_id,
        "source_sha256": source_hash(repository, execution_id),
        "execution_status": repository.get(execution_id).metadata["status"],
        "generated_at": _now(),
    }
    path = report_path(repository, execution_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, dump_document(metadata, body))
    return path


def is_execution_report_stale(
    repository: MarkdownRepository, execution_id: str
) -> bool | None:
    """Whether the saved report no longer matches its execution.

    ``None`` means there is no saved report.
    """
    path = report_path(repository, execution_id)
    if not path.is_file():
        return None
    try:
        saved = read_document(path).metadata.get("source_sha256")
    except FrontmatterError:
        return True
    return saved != source_hash(repository, execution_id)


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_traceability_report(repository: MarkdownRepository) -> str:
    """The requirement-to-execution matrix of a project, with its gaps."""
    rows = matrix(repository)
    graph = build_graph(repository)
    summary = {
        "requirements": len(rows),
        "passed": sum(1 for r in rows if r.flag == "passed"),
        "with failures": sum(1 for r in rows if r.flag == "has failures"),
        "not executed": sum(1 for r in rows if r.flag == "not executed"),
        "without a test case": sum(1 for r in rows if r.flag == "no test case"),
    }
    lines = [
        "# Traceability",
        "",
        "## Summary",
        "",
        *(f"- {name.capitalize()}: {count}" for name, count in summary.items()),
        "",
        "## Requirements",
        "",
        "| Requirement | Title | Test cases and latest execution | Status |",
        "|---|---|---|---|",
    ]
    for row in rows:
        cases = "; ".join(f"[[{case}]] {text}" for case, text in row.cases) or "-"
        title = _cell(row.title)
        lines.append(
            f"| [[{row.requirement}]] | {title} | {_cell(cases)} | {row.flag} |"
        )
    gaps = [
        f"- [[{row.requirement}]] has no test case." for row in rows if not row.cases
    ]
    if "TC" in repository.prefixes:
        gaps += [
            f"- [[{case.id}]] is not linked to any requirement."
            for case in repository.list_records("TC").records
            if not any(other.startswith("REQ-") for other in graph.neighbours(case.id))
        ]
    lines += ["", "## Gaps", "", *(gaps or ["None found."])]
    lines += [
        "",
        "## Not covered by this report",
        "",
        "- Defects and pipelines: no defect or pipeline records exist yet, so they "
        "are not part of the chain.",
    ]
    return "\n".join(lines) + "\n"


def write_traceability_report(repository: MarkdownRepository) -> Path:
    """Generate and save the traceability report of a project."""
    metadata = {"report": "traceability", "generated_at": _now()}
    path = report_path(repository, "traceability")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(
        path, dump_document(metadata, render_traceability_report(repository))
    )
    return path
