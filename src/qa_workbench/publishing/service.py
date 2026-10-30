"""Drafting and publishing external issue comments (REQ-027).

A comment is drafted as a ``COMMENT`` record, then published only through the
action guard: a person approves *this exact text* (the approval is bound to its
SHA-256, so editing it afterwards needs a new approval), and every step lands in
the audit log. The record keeps what was sent, who wrote it, when, the state,
and what the server answered.

Rules from the specification: no comment without real evidence and real links;
it only posts a comment (never closes an issue or changes labels, assignees, or
state); and a result that is not certain is reported as such, never as success.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

from qa_workbench.core.secrets import find_secrets
from qa_workbench.integrations.errors import IntegrationError, UnreachableError
from qa_workbench.integrations.gitlab.client import GitLabClient
from qa_workbench.publishing import schema
from qa_workbench.security.guard import ActionGuard, ApprovalRequired
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository, Record

MAX_LENGTH = 100_000
_URL = re.compile(r"https?://[^\s)>\]]+")


class CommentError(Exception):
    """A comment cannot be drafted or published as asked."""


class PublishFailed(CommentError):
    """The publication did not complete; ``status`` is what was recorded."""

    def __init__(self, message: str, status: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class PostedNote:
    id: str
    url: str = ""


class CommentWriter(Protocol):
    """Posts a note on an issue. GitLab implements it; others can follow."""

    provider: str

    def issue_url(self, issue: int) -> str: ...

    def post_note(self, issue: int, body: str) -> PostedNote: ...


class GitLabComments:
    provider = "gitlab"

    def __init__(self, client: GitLabClient, base_url: str, project_path: str) -> None:
        self._client = client
        self._issues = f"{base_url.rstrip('/')}/{project_path}/-/issues"

    def issue_url(self, issue: int) -> str:
        return f"{self._issues}/{issue}"

    def post_note(self, issue: int, body: str) -> PostedNote:
        path = self._client.project_path(f"/issues/{issue}/notes")
        reply = self._client.post_json(path, {"body": body})
        note_id = reply.get("id") if isinstance(reply, dict) else None
        if note_id is None:
            raise UnreachableError(
                "GitLab",
                "the reply to the new comment has no id",
                endpoint=path,
                hint="The comment may exist; check the issue before retrying",
            )
        return PostedNote(str(note_id), f"{self.issue_url(issue)}#note_{note_id}")


def canonical(body: str) -> str:
    """The text exactly as it is stored, hashed, approved, and sent.

    The repository stores LF line endings and one final newline, so the hash is
    taken over that form: what a person approved is what is posted.
    """
    return body.replace("\r\n", "\n").strip("\n") + "\n"


def body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _check_body(body: str, allowed_hosts: Sequence[str]) -> list[str]:
    problems = []
    if not body.strip():
        problems.append("the comment is empty")
    if len(body) > MAX_LENGTH:
        problems.append(
            f"the comment is {len(body)} characters; the limit is {MAX_LENGTH}"
        )
    for leak in sorted(set(find_secrets(body))):
        problems.append(f"the comment contains {leak}")
    for url in _URL.findall(body):
        host = (urlsplit(url).hostname or "").lower()
        if not _host_listed(host, allowed_hosts):
            problems.append(
                f"the link {url} points to a host that is not authorized "
                "(only real, authorized links may be published)"
            )
    return problems


def _host_listed(host: str, allowed: Sequence[str]) -> bool:
    for entry in (a.lower() for a in allowed):
        if entry.startswith("."):
            if host.endswith(entry) and host != entry[1:]:
                return True
        elif host == entry:
            return True
    return False


def _check_references(
    repository: MarkdownRepository,
    evidence: Sequence[str],
    execution: str | None,
) -> list[str]:
    """Evidence and execution must exist and, for evidence, be intact."""
    problems = []
    if not evidence:
        problems.append(
            "a comment needs at least one evidence record (--evidence EVD-...)"
        )
    store = EvidenceStore(repository)
    for evidence_id in evidence:
        try:
            issues = store.verify(evidence_id)
        except StorageError as error:
            problems.append(f"{evidence_id}: {error}")
            continue
        problems += [f"{evidence_id}: {issue}" for issue in issues]
    if execution:
        try:
            repository.get(execution)
        except StorageError as error:
            problems.append(f"{execution}: {error}")
    return problems


def draft_comment(
    repository: MarkdownRepository,
    *,
    issue: int,
    body: str,
    author: str,
    writer: CommentWriter,
    allowed_hosts: Sequence[str],
    evidence: Sequence[str] = (),
    execution: str | None = None,
    requirements: Sequence[str] = (),
) -> Record:
    """Save a draft. Nothing is sent; every problem is reported at once."""
    body = canonical(body)
    problems = _check_body(body, [*allowed_hosts, _host_of(writer.issue_url(issue))])
    problems += _check_references(repository, evidence, execution)
    if not author.strip():
        problems.append("the comment needs an author")
    if problems:
        listed = "\n".join(f"  - {p}" for p in problems)
        raise CommentError(f"The comment cannot be drafted:\n{listed}")
    fields: dict[str, object] = {
        "status": schema.DRAFT,
        "title": f"Comment on {writer.provider} issue #{issue}",
        "provider": writer.provider,
        "issue": issue,
        "issue_url": writer.issue_url(issue),
        "author": author.strip(),
        "body_sha256": body_hash(body),
        "evidence": list(evidence),
    }
    if execution:
        fields["execution"] = execution
    if requirements:
        fields["requirements"] = list(requirements)
    return repository.create("COMMENT", fields, body)


def _host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def publish_comment(
    repository: MarkdownRepository,
    comment_id: str,
    *,
    guard: ActionGuard,
    writer: CommentWriter,
    checked_issue_for_unknown_outcome: bool = False,
) -> Record:
    """Publish a drafted comment if a person approved this exact text.

    Raises :class:`ApprovalRequired` (the record becomes ``awaiting_approval``),
    ``ApprovalDenied``, or :class:`PublishFailed`. Returns the sealed record on
    success.
    """
    record = repository.get(comment_id)
    status = record.metadata["status"]
    if status == schema.PUBLISHED:
        raise CommentError(f"{comment_id} is already published; it is never re-sent.")
    if status == schema.OUTCOME_UNKNOWN and not checked_issue_for_unknown_outcome:
        raise CommentError(
            f"The last attempt for {comment_id} may have posted the comment. Check "
            f"the issue ({record.metadata['issue_url']}) and, only if it is not "
            "there, publish again confirming you checked."
        )
    body = record.body
    if body_hash(body) != record.metadata["body_sha256"]:
        raise CommentError(
            f"{comment_id} was edited after it was drafted (its hash changed). "
            "Draft a new comment instead."
        )
    problems = _check_body(
        body, [*guard.settings.allowed_hosts, _host_of(record.metadata["issue_url"])]
    )
    problems += _check_references(
        repository,
        record.metadata.get("evidence", []),
        record.metadata.get("execution"),
    )
    if problems:
        listed = "\n".join(f"  - {p}" for p in problems)
        raise CommentError(f"{comment_id} cannot be published:\n{listed}")

    issue = int(record.metadata["issue"])
    action = ActionRequest(
        "publish issue comment",
        Category.EXTERNAL_COMMENT,
        f"{comment_id} on {record.metadata['issue_url']} "
        f"sha256:{record.metadata['body_sha256']}",
        target_url=record.metadata["issue_url"],
        requested_by=str(record.metadata["author"]),
    )
    try:
        guard.authorize(action)
    except ApprovalRequired:
        if status != schema.AWAITING_APPROVAL:
            repository.update(comment_id, {"status": schema.AWAITING_APPROVAL})
        raise

    try:
        note = writer.post_note(issue, body)
    except UnreachableError as error:
        return _fail(repository, guard, comment_id, schema.OUTCOME_UNKNOWN, str(error))
    except IntegrationError as error:
        return _fail(repository, guard, comment_id, schema.FAILED, str(error))

    published_at = datetime.now(UTC).astimezone()
    sealed = repository.update(
        comment_id,
        {
            "status": schema.PUBLISHED,
            "external_id": note.id,
            "external_url": note.url,
            "published_at": published_at,
        },
    )
    guard.audit.append(
        "comment_published",
        str(record.metadata["author"]),
        {
            "comment": comment_id,
            "issue_url": record.metadata["issue_url"],
            "external_id": note.id,
        },
    )
    return sealed


def _fail(
    repository: MarkdownRepository,
    guard: ActionGuard,
    comment_id: str,
    status: str,
    message: str,
) -> Record:
    repository.update(comment_id, {"status": status, "last_error": message})
    guard.audit.append(
        "comment_failed",
        "qa-workbench",
        {"comment": comment_id, "status": status, "error": message},
    )
    raise PublishFailed(message, status)
