"""Import requirements from the GitLab group wiki (REQ-009).

One wiki page is one requirement. Each record keeps where it came from: the page
slug, its URL, the SHA-256 of the text, and when it was read. Importing again is
safe: a page that did not change is skipped, and a page that changed updates its
record in place (the history keeps the earlier text) and sends it back to draft,
so a person reviews the change instead of finding a second record.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from qa_workbench.integrations.gitlab.wiki import (
    WikiPage,
    business_rules,
    page_url,
    requirement_codes,
)
from qa_workbench.requirements.importer import ImportIssue
from qa_workbench.requirements.schema import DRAFT
from qa_workbench.storage.errors import RecordFinalizedError, RecordValidationError
from qa_workbench.storage.repository import MarkdownRepository, Record

SOURCE_KIND = "GitLab wiki"


@dataclass(frozen=True)
class WikiImportReport:
    created: tuple[Record, ...]
    updated: tuple[Record, ...]
    skipped: tuple[str, ...]
    issues: tuple[ImportIssue, ...]


def _digest(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def import_wiki_pages(
    repository: MarkdownRepository,
    pages: Sequence[WikiPage],
    *,
    base_url: str,
    group: str,
) -> WikiImportReport:
    """Create or update one requirement per page. Pages with problems are
    reported and skipped; the rest are imported."""
    existing = {
        r.metadata.get("source_ref"): r
        for r in repository.list_records("REQ").records
        if str(r.metadata.get("source", "")).startswith(SOURCE_KIND)
    }
    created: list[Record] = []
    updated: list[Record] = []
    skipped: list[str] = []
    issues: list[ImportIssue] = []
    stamp = datetime.now().astimezone()
    for page in pages:
        if not page.content.strip():
            issues.append(ImportIssue(page.slug, "the page is empty"))
            continue
        digest = _digest(page.content)
        fields: dict[str, object] = {
            "title": page.title,
            "source": f"{SOURCE_KIND} {group}",
            "source_ref": page.slug,
            "source_url": page_url(base_url, group, page.slug),
            "source_sha256": digest,
            "source_format": page.format,
            "imported_at": stamp,
            "origin": "imported",
        }
        codes = requirement_codes(page.slug, page.title)
        rules = business_rules(page.content)
        if codes:
            fields["tags"] = codes
        if rules:
            fields["business_rules"] = rules
        body = f"# {page.title}\n\n{page.content.strip()}\n"
        known = existing.get(page.slug)
        try:
            if known is None:
                created.append(
                    repository.create("REQ", {**fields, "status": DRAFT}, body)
                )
            elif known.metadata.get("source_sha256") == digest:
                skipped.append(known.id)
            else:
                updated.append(
                    repository.update(known.id, {**fields, "status": DRAFT}, body)
                )
        except (RecordValidationError, RecordFinalizedError) as error:
            problems = getattr(error, "problems", None) or [str(error)]
            issues.append(ImportIssue(page.slug, "; ".join(problems)))
    return WikiImportReport(
        tuple(created), tuple(updated), tuple(skipped), tuple(issues)
    )
