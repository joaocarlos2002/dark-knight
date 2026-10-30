from pathlib import Path

import pytest

from qa_workbench.requirements.schema import (
    REQUIREMENT_SCHEMA,
)
from qa_workbench.requirements.schema import REVIEW_POLICY as REQUIREMENT_POLICY
from qa_workbench.review.service import ReviewError, ReviewService
from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import Step, TestCaseDraft
from qa_workbench.testcases.schema import REVIEW_POLICY as CASE_POLICY
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(
        tmp_path / "project", [REQUIREMENT_SCHEMA, TEST_CASE_SCHEMA]
    )


@pytest.fixture
def service(repo: MarkdownRepository) -> ReviewService:
    return ReviewService(repo, {"REQ": REQUIREMENT_POLICY, "TC": CASE_POLICY})


def _requirement(repo: MarkdownRepository, **extra: object):
    fields = {
        "title": "Users can log in",
        "status": "draft",
        "source": "spec.md",
        "origin": "ai",
        "generated_by": "opencode",
        **extra,
    }
    return repo.create("REQ", fields, "# Users can log in\n")


def _ai_case(repo: MarkdownRepository):
    draft = TestCaseDraft(
        title="Log in",
        objective="Validate login",
        steps=[Step("Submit credentials")],
        expected_result="Authenticated",
        origin="ai",
    )
    fields = draft.to_fields()
    fields["generated_by"] = "opencode"
    return repo.create("TC", fields, "# Log in\n")


def test_an_ai_record_waits_for_review_and_is_listed_as_pending(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)
    _requirement(repo, origin="manual", generated_by=None, title="Manual one")

    assert [r.id for r in service.pending()] == [record.id]


def test_the_full_path_to_approval(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)

    submitted = service.submit(record.id)
    approved = service.decide(record.id, "Ana", "approved", "Matches the spec.")

    assert submitted.metadata["status"] == "in_review"
    assert approved.metadata["status"] == "approved"
    (review,) = approved.metadata["reviews"]
    assert review["reviewer"] == "Ana"
    assert review["decision"] == "approved"
    assert review["comment"] == "Matches the spec."
    assert review["timestamp"].utcoffset() is not None
    assert service.pending() == []
    assert repo.get(record.id).metadata["status"] == "approved"


def test_ai_records_cannot_skip_the_review(repo: MarkdownRepository) -> None:
    record = _requirement(repo)

    with pytest.raises(RecordValidationError, match="cannot be approved without"):
        repo.update(record.id, {"status": "approved"})

    assert repo.get(record.id).metadata["status"] == "draft"


def test_the_generator_cannot_approve_its_own_work(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)
    service.submit(record.id)

    with pytest.raises(RecordValidationError, match="different person"):
        service.decide(record.id, "OpenCode", "approved")

    assert repo.get(record.id).metadata["status"] == "in_review"
    assert "reviews" not in repo.get(record.id).metadata


def test_a_rejection_is_recorded_and_closes_the_review(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)
    service.submit(record.id)

    rejected = service.decide(record.id, "Ana", "rejected", "Not in scope.")

    assert rejected.metadata["status"] == "rejected"
    assert service.pending() == []


def test_changes_requested_sends_it_back_to_draft_and_it_can_be_resubmitted(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)
    service.submit(record.id)

    back = service.decide(record.id, "Ana", "changes_requested", "Add criteria.")
    again = service.submit(record.id)
    approved = service.decide(record.id, "Bruno", "approved")

    assert back.metadata["status"] == "draft"
    assert again.metadata["status"] == "in_review"
    assert [r["decision"] for r in approved.metadata["reviews"]] == [
        "changes_requested",
        "approved",
    ]


def test_a_test_case_is_activated_by_an_approving_review(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    case = _ai_case(repo)
    service.submit(case.id)

    done = service.decide(case.id, "Ana", "approved")

    assert done.metadata["status"] == "active"


def test_manual_records_can_go_through_review_too(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo, origin="manual", generated_by=None)
    service.submit(record.id)

    assert service.decide(record.id, "Ana", "approved").metadata["status"] == "approved"


def test_manual_records_can_be_approved_directly(repo: MarkdownRepository) -> None:
    record = _requirement(repo, origin="manual", generated_by=None)

    assert (
        repo.update(record.id, {"status": "approved"}).metadata["status"] == "approved"
    )


def test_only_a_draft_can_be_submitted(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)
    service.submit(record.id)

    with pytest.raises(ReviewError, match="only a draft can be submitted"):
        service.submit(record.id)


def test_only_a_record_in_review_can_be_decided(
    repo: MarkdownRepository, service: ReviewService
) -> None:
    record = _requirement(repo)

    with pytest.raises(ReviewError, match="submit it for review before deciding"):
        service.decide(record.id, "Ana", "approved")


@pytest.mark.parametrize(
    ("reviewer", "decision", "message"),
    [
        (" ", "approved", "needs a reviewer"),
        ("Ana", "maybe", "decision must be one of"),
    ],
)
def test_invalid_decisions_are_refused(
    repo: MarkdownRepository,
    service: ReviewService,
    reviewer: str,
    decision: str,
    message: str,
) -> None:
    record = _requirement(repo)
    service.submit(record.id)

    with pytest.raises(ValueError, match=message):
        service.decide(record.id, reviewer, decision)


def test_kinds_without_a_policy_do_not_go_through_review(
    repo: MarkdownRepository,
) -> None:
    service = ReviewService(repo, {"REQ": REQUIREMENT_POLICY})
    case = _ai_case(repo)

    with pytest.raises(ReviewError, match="does not go through review"):
        service.submit(case.id)


def test_a_hand_edited_approval_is_caught_when_read(
    repo: MarkdownRepository,
) -> None:
    record = _requirement(repo)
    record.path.write_text(
        record.path.read_text(encoding="utf-8").replace(
            "status: draft", "status: approved"
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecordValidationError, match="cannot be approved without"):
        repo.get(record.id)


def test_findings_are_stored_and_a_fact_without_a_source_is_refused(
    repo: MarkdownRepository,
) -> None:
    good = _requirement(
        repo,
        ai_findings=[
            {
                "kind": "fact",
                "text": "Spec section 2 requires it.",
                "source": "REQ-001",
            },
            {"kind": "hypothesis", "text": "Maybe SSO applies."},
        ],
    )

    assert [f["kind"] for f in good.metadata["ai_findings"]] == ["fact", "hypothesis"]
    with pytest.raises(RecordValidationError, match="fact without a source"):
        _requirement(repo, ai_findings=[{"kind": "fact", "text": "Trust me."}])
