"""Submit records for review and record human decisions."""

from collections.abc import Mapping
from datetime import datetime

from qa_workbench.review.policy import (
    AI_ORIGIN,
    APPROVED,
    CHANGES_REQUESTED,
    DECISIONS,
    DRAFT,
    IN_REVIEW,
    REJECTED,
    ReviewPolicy,
)
from qa_workbench.storage.ids import parse_id
from qa_workbench.storage.repository import MarkdownRepository, Record


class ReviewError(Exception):
    """Raised when a review step is not allowed in the record's current state."""


class ReviewService:
    """The review workflow: draft, in review, then approved, rejected, or back.

    ``policies`` maps a record prefix to its approved and rejected statuses.
    """

    def __init__(
        self, repository: MarkdownRepository, policies: Mapping[str, ReviewPolicy]
    ) -> None:
        self._repository = repository
        self._policies = dict(policies)

    def submit(self, record_id: str) -> Record:
        """Ask for review: a draft moves to ``in_review``."""
        record = self._repository.get(record_id)
        self._policy(record_id)
        status = record.metadata["status"]
        if status != DRAFT:
            raise ReviewError(
                f"{record_id} is {status}; only a draft can be submitted for review."
            )
        return self._repository.update(record_id, {"status": IN_REVIEW})

    def decide(
        self, record_id: str, reviewer: str, decision: str, comment: str = ""
    ) -> Record:
        """Record a human decision on a record that is in review."""
        policy = self._policy(record_id)
        if not reviewer.strip():
            raise ValueError("A review needs a reviewer.")
        if decision not in DECISIONS:
            raise ValueError(f"decision must be one of: {', '.join(DECISIONS)}.")
        record = self._repository.get(record_id)
        status = record.metadata["status"]
        if status != IN_REVIEW:
            raise ReviewError(
                f"{record_id} is {status}; submit it for review before deciding."
            )
        outcome = {
            APPROVED: policy.approved_status,
            REJECTED: policy.rejected_status,
            CHANGES_REQUESTED: DRAFT,
        }[decision]
        review = {
            "reviewer": reviewer.strip(),
            "decision": decision,
            "timestamp": datetime.now().astimezone(),
            "comment": comment.strip(),
        }
        reviews = [*(record.metadata.get("reviews") or []), review]
        return self._repository.update(
            record_id, {"status": outcome, "reviews": reviews}
        )

    def pending(self) -> list[Record]:
        """AI-generated records still waiting for a human decision."""
        waiting: list[Record] = []
        for prefix in sorted(self._policies):
            for record in self._repository.list_records(prefix).records:
                metadata = record.metadata
                if metadata.get("origin") == AI_ORIGIN and metadata["status"] in {
                    DRAFT,
                    IN_REVIEW,
                }:
                    waiting.append(record)
        return waiting

    def _policy(self, record_id: str) -> ReviewPolicy:
        prefix = parse_id(record_id).prefix
        try:
            return self._policies[prefix]
        except KeyError:
            raise ReviewError(
                f"{record_id}: this kind of record does not go through review."
            ) from None
