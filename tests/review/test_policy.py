from datetime import UTC, datetime
from typing import Any

import pytest

from qa_workbench.review.policy import ReviewPolicy, review_checks

NOW = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
CHECK = review_checks(ReviewPolicy("approved", "rejected"))


def _ai(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "origin": "ai",
        "generated_by": "opencode",
        "status": "draft",
        "author": "alfred",
    }
    values.update(overrides)
    return values


def _review(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "reviewer": "Ana",
        "decision": "approved",
        "timestamp": NOW,
        "comment": "Looks right.",
    }
    values.update(overrides)
    return values


def test_a_draft_ai_record_needs_no_review_yet() -> None:
    assert CHECK(_ai()) == []


def test_manual_records_are_not_gated() -> None:
    assert CHECK({"origin": "manual", "status": "approved"}) == []
    assert CHECK({"origin": "imported", "status": "approved"}) == []


def test_an_ai_record_needs_to_say_what_generated_it() -> None:
    problems = CHECK(_ai(generated_by=" "))

    assert problems == [
        "an AI-generated record needs generated_by (the provider or model)."
    ]


def test_an_ai_record_cannot_be_approved_without_a_review() -> None:
    problems = CHECK(_ai(status="approved"))

    assert problems == [
        "an AI-generated record cannot be approved without a human review "
        "that approves it."
    ]


def test_the_last_review_must_approve() -> None:
    reviews = [_review(), _review(decision="changes_requested")]

    assert CHECK(_ai(status="approved", reviews=reviews))


def test_an_approving_review_allows_approval() -> None:
    assert CHECK(_ai(status="approved", reviews=[_review()])) == []


def test_other_statuses_do_not_need_an_approving_review() -> None:
    assert CHECK(_ai(status="rejected", reviews=[_review(decision="rejected")])) == []
    assert CHECK(_ai(status="in_review")) == []


@pytest.mark.parametrize("reviewer", ["opencode", "OpenCode", " alfred "])
def test_the_reviewer_cannot_be_the_generator_or_the_author(reviewer: str) -> None:
    problems = CHECK(_ai(status="approved", reviews=[_review(reviewer=reviewer)]))

    assert problems == [
        "the reviewer must be a different person from the generator and the author."
    ]


def test_the_policy_uses_its_own_approved_status() -> None:
    check = review_checks(ReviewPolicy("active", "rejected"))

    assert check(_ai(status="approved")) == []
    assert check(_ai(status="active"))


# --- findings -----------------------------------------------------------------


def test_each_kind_of_finding_is_accepted() -> None:
    findings = [
        {"kind": "fact", "text": "The spec requires login.", "source": "REQ-001"},
        {"kind": "hypothesis", "text": "Lockout may apply."},
        {"kind": "recommendation", "text": "Add a boundary test."},
        {"kind": "inconclusive", "text": "No data for SSO.", "source": "EVD-002"},
    ]

    assert CHECK(_ai(ai_findings=findings)) == []


def test_a_fact_must_cite_a_source() -> None:
    problems = CHECK(_ai(ai_findings=[{"kind": "fact", "text": "It works."}]))

    assert problems == [
        "finding 1 is a fact without a source; cite the record that supports it "
        "or mark it as a hypothesis."
    ]


@pytest.mark.parametrize("source", ["the spec", "http://x.test", "REQ-1", 42])
def test_a_source_must_be_a_real_record_id(source: Any) -> None:
    findings = [{"kind": "fact", "text": "x", "source": source}]

    problems = CHECK(_ai(ai_findings=findings))

    assert len(problems) == 1
    assert "must be the id of a record" in problems[0]


@pytest.mark.parametrize(
    ("finding", "fragment"),
    [
        ({"kind": "opinion", "text": "x"}, "kind 'opinion' is not allowed"),
        ({"kind": "hypothesis", "text": " "}, "needs a text"),
        ({"kind": "hypothesis"}, "needs a text"),
        ({"kind": "hypothesis", "text": "x", "extra": 1}, "unknown fields"),
        ("just text", "must have a kind and a text"),
    ],
)
def test_malformed_findings_are_reported(finding: Any, fragment: str) -> None:
    problems = CHECK(_ai(ai_findings=[finding]))

    assert any(fragment in p for p in problems)


def test_findings_must_be_a_list() -> None:
    assert CHECK(_ai(ai_findings="x")) == ["ai_findings must be a list."]


def test_findings_are_checked_on_any_record() -> None:
    problems = CHECK(
        {"origin": "manual", "status": "draft", "ai_findings": [{"kind": "fact"}]}
    )

    assert problems


# --- reviews ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("review", "fragment"),
    [
        (_review(reviewer=" "), "needs a reviewer"),
        (_review(decision="maybe"), "decision 'maybe' is not allowed"),
        (_review(timestamp=datetime(2026, 1, 1)), "timezone"),
        (_review(timestamp="today"), "timezone"),
        (_review(comment=5), "comment must be text"),
        ("not a mapping", "must be a mapping"),
    ],
)
def test_malformed_reviews_are_reported(review: Any, fragment: str) -> None:
    problems = CHECK(_ai(reviews=[review]))

    assert any(fragment in p for p in problems)


def test_reviews_must_be_a_list() -> None:
    assert CHECK(_ai(reviews="x")) == ["reviews must be a list."]
