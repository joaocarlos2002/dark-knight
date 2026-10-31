"""Opening a GitLab issue from a confirmed finding, with its evidence (#167).

This is an outward-facing write, so it follows the same rules as a comment: a
person other than the finding's author approves *this exact action* (the request
names the finding, the issue text by its SHA-256, and every file that would be
uploaded), the host must be allowed, the text is checked for secrets, and each
step is audited.

Only a finding that is ``reproduced`` can be published, as a plain issue (never
a test case). The issue is created once: its iid and URL are written on the
finding and a second publish reports the existing one. Evidence files are
uploaded to the **same project** as the issue, so the embedded images resolve.
GitLab uploads cannot be deleted through the workbench, and the approval
request says so.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from qa_workbench.bughunt.schema import REPRODUCED
from qa_workbench.integrations.errors import IntegrationError, UnreachableError
from qa_workbench.integrations.gitlab.client import DEFAULT_TOKEN_ENV, GitLabClient
from qa_workbench.integrations.gitlab.connect import open_writer
from qa_workbench.integrations.http import HttpGateway
from qa_workbench.publishing.service import _check_body, _host_of
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository, Record

UNKNOWN = "outcome_unknown"
CREATED = "created"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class BugPublishError(Exception):
    """A finding cannot be published as asked."""


@dataclass(frozen=True)
class PublishedBug:
    bug: str
    iid: int
    url: str
    already: bool = False


class GitLabBugs:
    """Creates issues and uploads files in one GitLab project."""

    def __init__(self, client: GitLabClient, base_url: str, project_path: str) -> None:
        self._client = client
        self.issues_url = f"{base_url.rstrip('/')}/{project_path}/-/issues"

    def upload(self, filename: str, content: bytes) -> str:
        """Upload a file and return the Markdown that embeds it."""
        reply = self._client.upload_file(filename, content)
        markdown = reply.get("markdown") if isinstance(reply, dict) else None
        if not isinstance(markdown, str) or not markdown:
            raise UnreachableError(
                "GitLab",
                "the reply to the upload has no Markdown",
                endpoint="uploads",
                hint="The file may be uploaded; it cannot be removed from here",
            )
        return markdown

    def create_issue(self, title: str, description: str) -> tuple[int, str]:
        """A plain issue (no issue_type other than the default)."""
        path = self._client.project_path("/issues")
        reply = self._client.post_json(
            path, {"title": title, "description": description, "issue_type": "issue"}
        )
        iid = reply.get("iid") if isinstance(reply, dict) else None
        if not isinstance(iid, int):
            raise UnreachableError(
                "GitLab",
                "the reply to the new issue has no iid",
                endpoint=path,
                hint="The issue may exist; check GitLab before retrying",
            )
        return iid, f"{self.issues_url}/{iid}"


def open_publisher(
    project_id: str,
    gateway: HttpGateway,
    *,
    url: str | None = None,
    token_env: str = DEFAULT_TOKEN_ENV,
    data_dir: Path | None = None,
) -> tuple[GitLabBugs, ActionGuard]:
    """The writer for the project's GitLab and the guard that must approve."""
    client, guard = open_writer(
        project_id, gateway, url=url, token_env=token_env, data_dir=data_dir
    )
    return GitLabBugs(client, client.base_url, client.project_name), guard


def _section(heading: str, text: str) -> list[str]:
    return [f"## {heading}", text] if text.strip() else []


def issue_title(bug: Record) -> str:
    return str(bug.metadata["title"]).strip()


def issue_description(bug: Record, uploads: dict[str, str] | None = None) -> str:
    """The issue text. ``uploads`` maps an evidence id to the Markdown that
    embeds its uploaded file; without it the evidence is listed by id."""
    meta = bug.metadata
    steps = "\n".join(f"{n}. {s}" for n, s in enumerate(meta.get("steps", []), 1))
    evidence = "\n".join(
        f"- {e}: {uploads[e]}" if uploads and e in uploads else f"- {e}"
        for e in meta.get("evidence", [])
    )
    parts = [
        f"**Environment:** {meta['environment']}",
        f"**Reproduced:** {meta.get('reproductions', 0)} of "
        f"{meta.get('attempts', 0)} attempts",
    ]
    if meta.get("severity"):
        parts.append(f"**Proposed severity:** {meta['severity']}")
    for heading, text in (
        ("Context", str(meta.get("context", ""))),
        ("Steps to reproduce", steps),
        ("Expected result", str(meta.get("expected", ""))),
        ("Observed result", str(meta.get("observed", ""))),
        ("Evidence", evidence),
        ("Impact", str(meta.get("impact", ""))),
        ("Limitations", str(meta.get("limitations", ""))),
    ):
        parts += _section(heading, text)
    parts.append(f"_Recorded in the QA workbench as {bug.id}._")
    return "\n\n".join(parts) + "\n"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _evidence_files(
    repository: MarkdownRepository, evidence_ids: Sequence[str]
) -> list[tuple[str, str, bytes]]:
    """(id, file name, content) of every evidence file, after verifying it."""
    store = EvidenceStore(repository)
    files = []
    for evidence_id in evidence_ids:
        try:
            problems = store.verify(evidence_id)
            record = store.get(evidence_id)
            path = store.file_path(record)
            if problems:
                raise BugPublishError(f"{evidence_id}: {'; '.join(problems)}")
            if path.stat().st_size > MAX_UPLOAD_BYTES:
                raise BugPublishError(
                    f"{evidence_id} is larger than "
                    f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB; GitLab may refuse it"
                )
            files.append((evidence_id, path.name, path.read_bytes()))
        except (StorageError, OSError) as error:
            raise BugPublishError(f"{evidence_id}: {error}") from error
    return files


def check_publishable(bug: Record, allowed_hosts: Sequence[str], base: str) -> None:
    """Raise unless this finding may go out. Every problem is listed at once."""
    meta = bug.metadata
    problems = []
    if meta["status"] != REPRODUCED:
        problems.append(
            f"{bug.id} is {meta['status']}; only a reproduced defect with evidence "
            "can be published as a bug"
        )
    if not meta.get("evidence"):
        problems.append("a bug needs at least one evidence record")
    text = issue_title(bug) + "\n" + issue_description(bug)
    problems += _check_body(text, [*allowed_hosts, base])
    if problems:
        listed = "\n".join(f"  - {p}" for p in dict.fromkeys(problems))
        raise BugPublishError(f"{bug.id} cannot be published:\n{listed}")


def publish_bug(
    repository: MarkdownRepository,
    bug_id: str,
    *,
    guard: ActionGuard,
    writer: GitLabBugs,
    checked_issue_for_unknown_outcome: bool = False,
) -> PublishedBug:
    """Open the issue if a person approved this exact action.

    Raises ``ApprovalRequired`` (carrying the request id) or
    :class:`BugPublishError`. A finding that already has an issue returns it.
    """
    try:
        bug = repository.get(bug_id)
    except StorageError as error:
        raise BugPublishError(str(error)) from error
    meta = bug.metadata
    if meta.get("gitlab_issue_iid"):
        return PublishedBug(
            bug_id, int(meta["gitlab_issue_iid"]), str(meta["gitlab_issue_url"]), True
        )
    if meta.get("gitlab_publish") == UNKNOWN and not checked_issue_for_unknown_outcome:
        raise BugPublishError(
            f"The last attempt for {bug_id} may have created the issue. Check "
            f"{writer.issues_url} and, only if it is not there, publish again "
            "confirming you checked."
        )
    base = _host_of(writer.issues_url)
    check_publishable(bug, guard.settings.allowed_hosts, base)
    files = _evidence_files(repository, meta["evidence"])
    already = dict(meta.get("gitlab_uploads", {}))
    pending = [f for f in files if f[0] not in already]

    shown = "; ".join(
        f"{i} ({name}, sha256:{hashlib.sha256(content).hexdigest()[:12]})"
        for i, name, content in files
    )
    action = ActionRequest(
        "open GitLab issue from finding",
        Category.EXTERNAL_COMMENT,
        f"{bug_id} -> new issue in {writer.issues_url}; "
        f"text sha256:{_digest(issue_title(bug) + issue_description(bug))}; "
        f"uploads {len(files)} file(s) that cannot be deleted from the "
        f"workbench: {shown or 'none'}",
        target_url=writer.issues_url,
        requested_by=str(meta["found_by"]),
    )
    guard.authorize(action)  # raises ApprovalRequired until someone else approves

    uploads = already
    try:
        for evidence_id, name, content in pending:
            uploads[evidence_id] = writer.upload(name, content)
            repository.update(bug_id, {"gitlab_uploads": dict(uploads)})
        iid, url = writer.create_issue(
            issue_title(bug), issue_description(bug, uploads)
        )
    except UnreachableError as error:
        repository.update(bug_id, {"gitlab_publish": UNKNOWN, "last_error": str(error)})
        guard.audit.append(
            "bug_publish_failed",
            str(meta["found_by"]),
            {"bug": bug_id, "status": UNKNOWN, "error": str(error)},
        )
        raise BugPublishError(f"{error} (recorded as {UNKNOWN})") from error
    except IntegrationError as error:
        guard.audit.append(
            "bug_publish_failed",
            str(meta["found_by"]),
            {"bug": bug_id, "status": "failed", "error": str(error)},
        )
        raise BugPublishError(str(error)) from error

    repository.update(
        bug_id,
        {
            "gitlab_publish": CREATED,
            "gitlab_issue_iid": iid,
            "gitlab_issue_url": url,
            "gitlab_published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    guard.audit.append(
        "bug_published",
        str(meta["found_by"]),
        {"bug": bug_id, "issue_url": url, "uploads": sorted(uploads)},
    )
    return PublishedBug(bug_id, iid, url)
