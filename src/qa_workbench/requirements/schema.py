"""Requirement records (REQ-010)."""

from qa_workbench.storage.validation import RecordSchema

DRAFT = "draft"
STATUSES = frozenset({DRAFT, "in_review", "approved", "rejected", "obsolete"})
PRIORITIES = ("high", "medium", "low")

REQUIREMENT_SCHEMA = RecordSchema(
    prefix="REQ",
    directory="requirements",
    statuses=STATUSES,
    required=("title", "source"),
    optional_timestamps=("imported_at",),
    references={"cases": ("TC",), "issues": ("ISSUE",)},
    choices={"priority": frozenset(PRIORITIES)},
    text_lists=("acceptance_criteria", "tags"),
)
