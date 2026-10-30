"""Import requirements into a project (REQ-009).

The source file is read, never changed. Each requirement keeps where it came
from: the file name, the line, the SHA-256 of the file, the format, and an
optional version label, plus the author. Importing the same file twice does not
create duplicates.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from qa_workbench.requirements.parser import (
    ParsedRequirement,
    ParseResult,
    parse_markdown,
    parse_text,
)
from qa_workbench.requirements.schema import DRAFT
from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.history import sha256_file
from qa_workbench.storage.repository import MarkdownRepository, Record

MAX_SOURCE_BYTES = 5 * 1024 * 1024

_FORMATS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".text": "text",
}


class RequirementImportError(Exception):
    """Raised when a source cannot be imported at all."""


@dataclass(frozen=True)
class ImportIssue:
    """A requirement (or the whole file) that could not be imported, and why."""

    location: str
    message: str


@dataclass(frozen=True)
class ImportReport:
    """What an import did."""

    created: tuple[Record, ...]
    skipped: tuple[str, ...]
    issues: tuple[ImportIssue, ...]


def _body(parsed: ParsedRequirement) -> str:
    parts = [f"# {parsed.title}"]
    if parsed.description:
        parts.append(parsed.description)
    if parsed.acceptance_criteria:
        criteria = "\n".join(f"- {item}" for item in parsed.acceptance_criteria)
        parts.append(f"## Acceptance criteria\n\n{criteria}")
    return "\n\n".join(parts) + "\n"


def _read_source(source: Path, format_name: str | None) -> tuple[str, str]:
    if not source.is_file():
        raise RequirementImportError(f"{source} is not a file.")
    size = source.stat().st_size
    if size == 0:
        raise RequirementImportError(f"{source.name} is empty.")
    if size > MAX_SOURCE_BYTES:
        raise RequirementImportError(
            f"{source.name} is {size} bytes; the limit is {MAX_SOURCE_BYTES}."
        )
    chosen = format_name or _FORMATS.get(source.suffix.lower())
    if chosen not in {"markdown", "text"}:
        raise RequirementImportError(
            f"{source.name}: unsupported file type {source.suffix!r}. Use .md or "
            ".txt (PDF, DOCX, and XLSX are not supported yet)."
        )
    try:
        return chosen, source.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise RequirementImportError(
            f"{source.name} is not valid UTF-8: {error}"
        ) from error


def import_requirements(
    repository: MarkdownRepository,
    source: Path,
    *,
    author: str | None = None,
    source_version: str | None = None,
    format_name: str | None = None,
) -> ImportReport:
    """Import every requirement found in ``source``.

    ``author`` is the default author for requirements that do not name one.
    Requirements with problems are reported and skipped; the rest are imported.
    """
    chosen, text = _read_source(source, format_name)
    digest = sha256_file(source)
    parsed: ParseResult = (
        parse_markdown(text) if chosen == "markdown" else parse_text(text)
    )

    issues = [
        ImportIssue(f"{source.name}:{issue.line}", issue.message)
        for issue in parsed.issues
    ]
    if not parsed.requirements and not issues:
        raise RequirementImportError(f"No requirement found in {source.name}.")

    existing = {
        (
            r.metadata.get("source"),
            r.metadata.get("source_ref"),
            r.metadata.get("source_sha256"),
        ): r.id
        for r in repository.list_records("REQ").records
    }
    created: list[Record] = []
    skipped: list[str] = []
    imported_at = datetime.now().astimezone()
    for item in parsed.requirements:
        reference = f"line {item.line}"
        known = existing.get((source.name, reference, digest))
        if known is not None:
            skipped.append(known)
            continue
        fields: dict[str, object] = {
            "title": item.title,
            "status": item.status or DRAFT,
            "source": source.name,
            "source_ref": reference,
            "source_sha256": digest,
            "source_format": chosen,
            "imported_at": imported_at,
        }
        optional = {
            "priority": item.priority,
            "author": item.author or (author.strip() if author else None),
            "source_version": source_version.strip() if source_version else None,
            "tags": list(item.tags),
            "acceptance_criteria": list(item.acceptance_criteria),
        }
        fields.update({key: value for key, value in optional.items() if value})
        try:
            created.append(repository.create("REQ", fields, _body(item)))
        except RecordValidationError as error:
            issues.append(
                ImportIssue(f"{source.name}:{item.line}", "; ".join(error.problems))
            )
    return ImportReport(tuple(created), tuple(skipped), tuple(issues))
