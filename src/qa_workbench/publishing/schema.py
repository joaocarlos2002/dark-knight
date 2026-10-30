"""``COMMENT`` records: a copy of every external comment (REQ-027, spec 5.17)."""

from qa_workbench.storage.validation import RecordSchema

DRAFT = "draft"
AWAITING_APPROVAL = "awaiting_approval"
PUBLISHED = "published"
FAILED = "failed"
OUTCOME_UNKNOWN = "outcome_unknown"

STATUSES = frozenset({DRAFT, AWAITING_APPROVAL, PUBLISHED, FAILED, OUTCOME_UNKNOWN})

# A published comment is a fact about what was sent: it is sealed.
COMMENT_SCHEMA = RecordSchema(
    prefix="COMMENT",
    directory="comments",
    statuses=STATUSES,
    required=("title", "provider", "issue", "issue_url", "author", "body_sha256"),
    optional_timestamps=("published_at",),
    immutable_statuses=frozenset({PUBLISHED}),
    references={
        "execution": ("EXEC",),
        "evidence": ("EVD",),
        "requirements": ("REQ",),
    },
)
