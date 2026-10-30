"""Human review rules for AI-generated records (REQ-013, REQ-029).

Rules, applied as schema checks so they hold when a record is created, updated,
and read back from a hand-edited file:

* An AI-generated record names what produced it (``generated_by``).
* Its findings say whether each statement is a fact, a hypothesis, a
  recommendation, or inconclusive. A fact must cite a real record id; anything
  without a source is a hypothesis. Nothing is invented as evidence.
* It cannot be approved without a recorded review by someone other than the
  generator and the author.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from qa_workbench.storage.ids import parse_id

DRAFT = "draft"
IN_REVIEW = "in_review"
AI_ORIGIN = "ai"

FACT = "fact"
KINDS = (FACT, "hypothesis", "recommendation", "inconclusive")

APPROVED = "approved"
REJECTED = "rejected"
CHANGES_REQUESTED = "changes_requested"
DECISIONS = (APPROVED, REJECTED, CHANGES_REQUESTED)


@dataclass(frozen=True)
class ReviewPolicy:
    """The statuses a record kind uses at the end of a review."""

    approved_status: str
    rejected_status: str


def _check_findings(metadata: Mapping[str, Any]) -> list[str]:
    findings = metadata.get("ai_findings")
    if findings is None:
        return []
    if not isinstance(findings, list):
        return ["ai_findings must be a list."]
    problems: list[str] = []
    for number, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            problems.append(f"finding {number} must have a kind and a text.")
            continue
        kind = item.get("kind")
        if kind not in KINDS:
            problems.append(
                f"finding {number}: kind {kind!r} is not allowed; use one of: "
                f"{', '.join(KINDS)}."
            )
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"finding {number} needs a text.")
        extra = set(item) - {"kind", "text", "source"}
        if extra:
            problems.append(f"finding {number} has unknown fields: {sorted(extra)}.")
        source = item.get("source")
        if source is not None:
            try:
                parse_id(str(source))
            except ValueError:
                problems.append(
                    f"finding {number}: source {source!r} must be the id of a record."
                )
        elif kind == FACT:
            problems.append(
                f"finding {number} is a fact without a source; cite the record "
                "that supports it or mark it as a hypothesis."
            )
    return problems


def _check_reviews(metadata: Mapping[str, Any]) -> list[str]:
    reviews = metadata.get("reviews")
    if reviews is None:
        return []
    if not isinstance(reviews, list):
        return ["reviews must be a list."]
    problems: list[str] = []
    for number, item in enumerate(reviews, start=1):
        if not isinstance(item, dict):
            problems.append(f"review {number} must be a mapping.")
            continue
        reviewer = item.get("reviewer")
        if not isinstance(reviewer, str) or not reviewer.strip():
            problems.append(f"review {number} needs a reviewer.")
        if item.get("decision") not in DECISIONS:
            problems.append(
                f"review {number}: decision {item.get('decision')!r} is not allowed; "
                f"use one of: {', '.join(DECISIONS)}."
            )
        stamp = item.get("timestamp")
        if not isinstance(stamp, datetime) or stamp.tzinfo is None:
            problems.append(f"review {number} needs a timestamp with a timezone.")
        comment = item.get("comment", "")
        if comment is not None and not isinstance(comment, str):
            problems.append(f"review {number}: comment must be text.")
    return problems


def _names(metadata: Mapping[str, Any], *keys: str) -> set[str]:
    return {str(metadata[key]).strip().lower() for key in keys if metadata.get(key)}


def review_checks(
    policy: ReviewPolicy,
) -> Callable[[Mapping[str, Any]], list[str]]:
    """Schema check enforcing the review rules for one record kind."""

    def check(metadata: Mapping[str, Any]) -> list[str]:
        problems = _check_findings(metadata) + _check_reviews(metadata)
        if metadata.get("origin") != AI_ORIGIN:
            return problems
        if not str(metadata.get("generated_by") or "").strip():
            problems.append(
                "an AI-generated record needs generated_by (the provider or model)."
            )
        if metadata.get("status") == policy.approved_status:
            reviews = metadata.get("reviews")
            last = reviews[-1] if isinstance(reviews, list) and reviews else None
            if not isinstance(last, dict) or last.get("decision") != APPROVED:
                problems.append(
                    "an AI-generated record cannot be approved without a human "
                    "review that approves it."
                )
            else:
                reviewer = str(last.get("reviewer") or "").strip().lower()
                if reviewer in _names(metadata, "generated_by", "author"):
                    problems.append(
                        "the reviewer must be a different person from the "
                        "generator and the author."
                    )
        return problems

    return check
