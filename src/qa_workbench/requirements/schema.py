"""Requirement records (REQ-010)."""

from qa_workbench.review.policy import ReviewPolicy, review_checks
from qa_workbench.storage.validation import RecordSchema

DRAFT = "draft"
STATUSES = frozenset({DRAFT, "in_review", "approved", "rejected", "obsolete"})
PRIORITIES = ("high", "medium", "low")
ORIGINS = frozenset({"manual", "imported", "ai"})
REVIEW_POLICY = ReviewPolicy(approved_status="approved", rejected_status="rejected")

REQUIREMENT_SCHEMA = RecordSchema(
    prefix="REQ",
    directory="requirements",
    statuses=STATUSES,
    required=("title", "source", "origin"),
    optional_timestamps=("imported_at",),
    references={"cases": ("TC",), "issues": ("ISSUE",)},
    choices={"priority": frozenset(PRIORITIES), "origin": ORIGINS},
    text_lists=("acceptance_criteria", "tags"),
    extra_checks=(review_checks(REVIEW_POLICY),),
)
