from pathlib import Path

import pytest

from qa_workbench.bughunt.schema import BUG_SCHEMA
from qa_workbench.bughunt.service import record_finding
from qa_workbench.integrations.errors import UnreachableError
from qa_workbench.publishing.bugs import BugPublishError, publish_bug
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, ApprovalRequired
from qa_workbench.security.settings import SecuritySettings
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository

ISSUES = "https://gitlab.test/group/app/-/issues"


class FakeWriter:
    issues_url = ISSUES

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.uploads: list[str] = []
        self.issues: list[tuple[str, str]] = []

    def upload(self, filename: str, content: bytes) -> str:
        self.uploads.append(filename)
        return f"![{filename}](/uploads/abc/{filename})"

    def create_issue(self, title: str, description: str) -> tuple[int, str]:
        if self.failure:
            raise self.failure
        self.issues.append((title, description))
        return 41, f"{ISSUES}/41"


@pytest.fixture
def repository(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "p", [EVIDENCE_SCHEMA, BUG_SCHEMA])


def _evidence(repository: MarkdownRepository, tmp_path: Path) -> str:
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    return (
        EvidenceStore(repository)
        .register(shot, source="manual", description="login page")
        .id
    )


def _bug(repository, tmp_path, **extra) -> str:
    fields = {
        "title": "Login fails",
        "environment": "staging",
        "found_by": "Ana",
        "classification": "reproduced",
        "steps": ["Open /login", "Submit"],
        "expected": "Dashboard",
        "observed": "500 error",
        "evidence": [_evidence(repository, tmp_path)],
        "attempts": 3,
        "reproductions": 3,
    }
    fields.update(extra)
    return record_finding(repository, **fields).id


def _guard(tmp_path: Path) -> ActionGuard:
    settings = SecuritySettings(allowed_hosts=("gitlab.test",))
    return ActionGuard(settings, AuditLog(tmp_path / "p"))


def _approved(repository, guard, bug_id, checked=False) -> None:
    with pytest.raises(ApprovalRequired) as asked:
        publish_bug(
            repository,
            bug_id,
            guard=guard,
            writer=FakeWriter(),
            checked_issue_for_unknown_outcome=checked,
        )
    guard.book.decide(asked.value.request_id, approve=True, by="Bea", reason="ok")


def test_nothing_is_sent_until_someone_else_approves(repository, tmp_path) -> None:
    bug_id = _bug(repository, tmp_path)
    writer = FakeWriter()

    with pytest.raises(ApprovalRequired) as asked:
        publish_bug(repository, bug_id, guard=_guard(tmp_path), writer=writer)

    assert writer.uploads == [] and writer.issues == []
    assert "cannot be deleted" in str(asked.value) or asked.value.request_id
    assert "gitlab_issue_iid" not in repository.get(bug_id).metadata


def test_an_approved_publish_uploads_then_creates_one_issue(
    repository, tmp_path
) -> None:
    bug_id = _bug(repository, tmp_path)
    guard = _guard(tmp_path)
    _approved(repository, guard, bug_id)
    writer = FakeWriter()

    done = publish_bug(repository, bug_id, guard=guard, writer=writer)

    assert (done.iid, done.url, done.already) == (41, f"{ISSUES}/41", False)
    assert writer.uploads == ["shot.png"]
    title, description = writer.issues[0]
    assert title == "Login fails" and "/uploads/abc/shot.png" in description
    meta = repository.get(bug_id).metadata
    assert meta["gitlab_issue_iid"] == 41 and meta["gitlab_issue_url"] == f"{ISSUES}/41"
    kinds = [e.kind for e in AuditLog(tmp_path / "p").entries()]
    assert "bug_published" in kinds


def test_publishing_twice_reports_the_existing_issue(repository, tmp_path) -> None:
    bug_id = _bug(repository, tmp_path)
    guard = _guard(tmp_path)
    _approved(repository, guard, bug_id)
    publish_bug(repository, bug_id, guard=guard, writer=FakeWriter())
    again = FakeWriter()

    done = publish_bug(repository, bug_id, guard=guard, writer=again)

    assert done.already and done.iid == 41
    assert again.uploads == [] and again.issues == []


def test_a_finding_that_is_not_reproduced_cannot_be_published(
    repository, tmp_path
) -> None:
    bug_id = _bug(
        repository,
        tmp_path,
        classification="suspected",
        reproductions=0,
    )

    with pytest.raises(BugPublishError, match="only a reproduced defect"):
        publish_bug(repository, bug_id, guard=_guard(tmp_path), writer=FakeWriter())


def test_a_link_to_a_host_that_is_not_allowed_is_refused(repository, tmp_path) -> None:
    bug_id = _bug(repository, tmp_path, observed="See http://evil.example/x")

    with pytest.raises(BugPublishError, match="not authorized"):
        publish_bug(repository, bug_id, guard=_guard(tmp_path), writer=FakeWriter())


def test_an_unknown_outcome_blocks_a_blind_retry(repository, tmp_path) -> None:
    bug_id = _bug(repository, tmp_path)
    guard = _guard(tmp_path)
    _approved(repository, guard, bug_id)
    broken = FakeWriter(UnreachableError("GitLab", "timed out", endpoint="issues"))

    with pytest.raises(BugPublishError, match="outcome_unknown"):
        publish_bug(repository, bug_id, guard=guard, writer=broken)
    assert repository.get(bug_id).metadata["gitlab_publish"] == "outcome_unknown"

    with pytest.raises(BugPublishError, match="may have created the issue"):
        publish_bug(repository, bug_id, guard=guard, writer=FakeWriter())

    _approved(repository, guard, bug_id, checked=True)  # an approval is single-use
    done = publish_bug(
        repository,
        bug_id,
        guard=guard,
        writer=FakeWriter(),
        checked_issue_for_unknown_outcome=True,
    )
    assert done.iid == 41


def test_uploads_made_before_a_failure_are_not_repeated(repository, tmp_path) -> None:
    bug_id = _bug(repository, tmp_path)
    guard = _guard(tmp_path)
    _approved(repository, guard, bug_id)
    broken = FakeWriter(UnreachableError("GitLab", "timed out", endpoint="issues"))
    with pytest.raises(BugPublishError):
        publish_bug(repository, bug_id, guard=guard, writer=broken)
    retry = FakeWriter()
    _approved(repository, guard, bug_id, checked=True)

    publish_bug(
        repository,
        bug_id,
        guard=guard,
        writer=retry,
        checked_issue_for_unknown_outcome=True,
    )

    assert broken.uploads == ["shot.png"] and retry.uploads == []
