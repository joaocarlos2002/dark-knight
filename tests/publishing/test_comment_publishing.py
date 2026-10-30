from pathlib import Path

import pytest

from qa_workbench.integrations.errors import (
    AuthenticationError,
    UnreachableError,
)
from qa_workbench.publishing.schema import COMMENT_SCHEMA
from qa_workbench.publishing.service import (
    CommentError,
    PostedNote,
    PublishFailed,
    body_hash,
    draft_comment,
    publish_comment,
)
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import (
    ActionGuard,
    ApprovalDenied,
    ApprovalRequired,
)
from qa_workbench.security.settings import SecuritySettings
from qa_workbench.storage.errors import RecordFinalizedError
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository

ISSUE_URL = "https://gitlab.test/group/app/-/issues/7"
GOOD = (
    "QA result: login works on staging.\n"
    "Expected: dashboard. Observed: dashboard.\n"
    f"See {ISSUE_URL}.\n"
)


class FakeWriter:
    provider = "gitlab"

    def __init__(self, outcome: object = None) -> None:
        self.outcome = outcome
        self.posted: list[tuple[int, str]] = []

    def issue_url(self, issue: int) -> str:
        return f"https://gitlab.test/group/app/-/issues/{issue}"

    def post_note(self, issue: int, body: str) -> PostedNote:
        self.posted.append((issue, body))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return PostedNote("991", f"{self.issue_url(issue)}#note_991")


@pytest.fixture
def repository(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "p", [EVIDENCE_SCHEMA, COMMENT_SCHEMA])


@pytest.fixture
def evidence_id(repository: MarkdownRepository, tmp_path: Path) -> str:
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    return (
        EvidenceStore(repository)
        .register(shot, source="manual", description="login page")
        .id
    )


def _guard(tmp_path: Path) -> ActionGuard:
    settings = SecuritySettings(allowed_hosts=("gitlab.test",))
    return ActionGuard(settings, AuditLog(tmp_path / "p"))


def _draft(repository, evidence_id, body=GOOD, **extra):
    return draft_comment(
        repository,
        issue=7,
        body=body,
        author="Agent QA",
        writer=FakeWriter(),
        allowed_hosts=("gitlab.test",),
        evidence=[evidence_id],
        **extra,
    )


def _approve(guard: ActionGuard, comment_id: str, repository, checked=False) -> None:
    with pytest.raises(ApprovalRequired) as asked:
        publish_comment(
            repository,
            comment_id,
            guard=guard,
            writer=FakeWriter(),
            checked_issue_for_unknown_outcome=checked,
        )
    guard.book.decide(asked.value.request_id, approve=True, by="Ana", reason="ok")


# -- drafting -------------------------------------------------------------------


def test_draft_keeps_the_text_hash_provider_and_references(
    repository, evidence_id
) -> None:
    record = _draft(repository, evidence_id)

    assert record.metadata["status"] == "draft"
    assert record.metadata["body_sha256"] == body_hash(GOOD)
    assert record.metadata["evidence"] == [evidence_id]
    assert record.metadata["provider"] == "gitlab"
    assert record.body == GOOD


def test_every_drafting_problem_is_reported_at_once(repository) -> None:
    with pytest.raises(CommentError) as error:
        draft_comment(
            repository,
            issue=7,
            body="Fixed! See https://evil.test/proof and password=hunter22",
            author=" ",
            writer=FakeWriter(),
            allowed_hosts=("gitlab.test",),
            evidence=["EVD-404"],
        )

    message = str(error.value)
    assert "literal password" in message
    assert "evil.test" in message and "not authorized" in message
    assert "EVD-404" in message and "needs an author" in message
    assert repository.record_ids("COMMENT") == []


def test_a_comment_without_evidence_is_refused(repository) -> None:
    with pytest.raises(CommentError, match="at least one evidence"):
        draft_comment(
            repository,
            issue=7,
            body=GOOD,
            author="Ana",
            writer=FakeWriter(),
            allowed_hosts=(),
        )


def test_tampered_evidence_blocks_the_draft(repository, evidence_id) -> None:
    EvidenceStore(repository).file_path(repository.get(evidence_id)).write_bytes(b"x!")

    with pytest.raises(CommentError, match=evidence_id):
        _draft(repository, evidence_id)


def test_empty_and_oversized_bodies_are_refused(repository, evidence_id) -> None:
    with pytest.raises(CommentError, match="empty"):
        _draft(repository, evidence_id, body="  ")
    with pytest.raises(CommentError, match="limit"):
        _draft(repository, evidence_id, body="x" * 100_001)


# -- publishing -----------------------------------------------------------------


def test_publishing_needs_approval_and_nothing_is_sent_before_it(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    guard, writer = _guard(tmp_path), FakeWriter()

    with pytest.raises(ApprovalRequired):
        publish_comment(repository, comment.id, guard=guard, writer=writer)

    assert writer.posted == []
    assert repository.get(comment.id).metadata["status"] == "awaiting_approval"
    assert guard.book.pending()[0].category == "external_comment"


def test_approved_comment_is_posted_once_recorded_and_sealed(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    guard, writer = _guard(tmp_path), FakeWriter()
    _approve(guard, comment.id, repository)

    sealed = publish_comment(repository, comment.id, guard=guard, writer=writer)

    assert writer.posted == [(7, GOOD)]
    assert sealed.metadata["status"] == "published"
    assert sealed.metadata["external_id"] == "991"
    assert sealed.metadata["external_url"].endswith("#note_991")
    assert sealed.metadata["published_at"] is not None
    with pytest.raises(RecordFinalizedError):
        repository.update(comment.id, {"author": "someone else"})
    with pytest.raises(CommentError, match="already published"):
        publish_comment(repository, comment.id, guard=guard, writer=writer)
    kinds = [e.kind for e in guard.audit.entries()]
    assert kinds == [
        "approval_requested",
        "approval_granted",
        "approval_used",
        "comment_published",
    ]


def test_the_author_cannot_approve_their_own_comment(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    guard = _guard(tmp_path)
    with pytest.raises(ApprovalRequired) as asked:
        publish_comment(repository, comment.id, guard=guard, writer=FakeWriter())

    from qa_workbench.security.guard import ApprovalError

    with pytest.raises(ApprovalError, match="cannot also decide"):
        guard.book.decide(asked.value.request_id, approve=True, by="Agent QA")


def test_denial_blocks_publication(repository, evidence_id, tmp_path) -> None:
    comment = _draft(repository, evidence_id)
    guard, writer = _guard(tmp_path), FakeWriter()
    with pytest.raises(ApprovalRequired) as asked:
        publish_comment(repository, comment.id, guard=guard, writer=writer)
    guard.book.decide(
        asked.value.request_id, approve=False, by="Ana", reason="wrong environment"
    )

    with pytest.raises(ApprovalDenied, match="wrong environment"):
        publish_comment(repository, comment.id, guard=guard, writer=writer)
    assert writer.posted == []


def test_editing_the_text_after_drafting_is_caught(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    repository.update(comment.id, {}, body="Something else entirely")

    with pytest.raises(CommentError, match="edited after it was drafted"):
        publish_comment(
            repository, comment.id, guard=_guard(tmp_path), writer=FakeWriter()
        )


def test_an_approval_for_one_text_does_not_cover_another(
    repository, evidence_id, tmp_path
) -> None:
    first = _draft(repository, evidence_id)
    second = _draft(repository, evidence_id, body=GOOD + "Extra line.\n")
    guard, writer = _guard(tmp_path), FakeWriter()
    _approve(guard, first.id, repository)

    with pytest.raises(ApprovalRequired):
        publish_comment(repository, second.id, guard=guard, writer=writer)
    assert writer.posted == []


def test_a_server_rejection_is_recorded_as_failed_not_success(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    guard = _guard(tmp_path)
    _approve(guard, comment.id, repository)
    writer = FakeWriter(AuthenticationError("GitLab", "the token is not allowed"))

    with pytest.raises(PublishFailed, match="not allowed") as failed:
        publish_comment(repository, comment.id, guard=guard, writer=writer)

    assert failed.value.status == "failed"
    record = repository.get(comment.id)
    assert record.metadata["status"] == "failed"
    assert "not allowed" in record.metadata["last_error"]
    assert guard.audit.entries()[-1].kind == "comment_failed"


def test_a_lost_connection_leaves_the_outcome_unknown_until_checked(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    guard = _guard(tmp_path)
    _approve(guard, comment.id, repository)
    lost = FakeWriter(UnreachableError("GitLab", "connection reset"))

    with pytest.raises(PublishFailed) as failed:
        publish_comment(repository, comment.id, guard=guard, writer=lost)
    assert failed.value.status == "outcome_unknown"

    with pytest.raises(CommentError, match="may have posted"):
        publish_comment(repository, comment.id, guard=guard, writer=FakeWriter())

    _approve(guard, comment.id, repository, checked=True)  # fresh approval
    ok = publish_comment(
        repository,
        comment.id,
        guard=guard,
        writer=FakeWriter(),
        checked_issue_for_unknown_outcome=True,
    )
    assert ok.metadata["status"] == "published"


def test_evidence_that_breaks_after_drafting_blocks_publication(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id)
    EvidenceStore(repository).file_path(repository.get(evidence_id)).write_bytes(b"x!")

    with pytest.raises(CommentError, match="cannot be published"):
        publish_comment(
            repository, comment.id, guard=_guard(tmp_path), writer=FakeWriter()
        )


def test_text_without_a_final_newline_or_with_crlf_still_publishes(
    repository, evidence_id, tmp_path
) -> None:
    comment = _draft(repository, evidence_id, body="QA: ok\r\nSecond line")
    guard, writer = _guard(tmp_path), FakeWriter()
    _approve(guard, comment.id, repository)

    publish_comment(repository, comment.id, guard=guard, writer=writer)

    assert writer.posted == [(7, "QA: ok\nSecond line\n")]
    expected = body_hash("QA: ok\nSecond line\n")
    assert repository.get(comment.id).metadata["body_sha256"] == expected
