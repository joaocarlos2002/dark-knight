"""``BUG`` records for exploratory bug hunting (spec 5.12, 11.2).

The status of a bug record *is* its classification. The one hard rule is that a
confirmed defect needs enough evidence: steps to reproduce, expected and
observed results, intact evidence records, and at least two reproductions.
Anything weaker stays a suspicion or inconclusive; nothing is promoted by
wording alone, and the rule is checked when a record is written and when it is
read back from a hand-edited file.
"""

from collections.abc import Mapping
from typing import Any

from qa_workbench.storage.validation import RecordSchema

REPRODUCED = "reproduced"
SUSPECTED = "suspected"
FALSE_POSITIVE = "false_positive"
ENVIRONMENT_UNAVAILABLE = "environment_unavailable"
INCONCLUSIVE = "inconclusive"

CLASSIFICATIONS = (
    REPRODUCED,
    SUSPECTED,
    FALSE_POSITIVE,
    ENVIRONMENT_UNAVAILABLE,
    INCONCLUSIVE,
)
MIN_REPRODUCTIONS = 2
SEVERITIES = ("critical", "high", "medium", "low")


def _text(metadata: Mapping[str, Any], name: str) -> str:
    value = metadata.get(name)
    return value.strip() if isinstance(value, str) else ""


def check_bug(metadata: Mapping[str, Any]) -> list[str]:
    """Rules a schema cannot express declaratively."""
    problems: list[str] = []
    status = metadata.get("status")
    attempts = metadata.get("attempts", 0)
    reproductions = metadata.get("reproductions", 0)
    for name, value in (("attempts", attempts), ("reproductions", reproductions)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            problems.append(f"{name} must be a whole number, 0 or more.")
            return problems
    if reproductions > attempts:
        problems.append("reproductions cannot be more than attempts.")
    if status == REPRODUCED:
        if not metadata.get("evidence"):
            problems.append("a reproduced defect needs at least one evidence record.")
        if not metadata.get("steps"):
            problems.append("a reproduced defect needs the steps to reproduce it.")
        if not _text(metadata, "expected") or not _text(metadata, "observed"):
            problems.append("a reproduced defect needs expected and observed results.")
        if reproductions < MIN_REPRODUCTIONS:
            problems.append(
                f"a reproduced defect needs at least {MIN_REPRODUCTIONS} "
                f"reproductions; this one has {reproductions}. Keep it suspected "
                "until it reproduces."
            )
    if status == FALSE_POSITIVE and not _text(metadata, "reason"):
        problems.append("a false positive needs the reason it is one.")
    if status == ENVIRONMENT_UNAVAILABLE and not _text(metadata, "environment_issue"):
        problems.append("an environment problem needs a description of what failed.")
    severity = metadata.get("severity")
    if severity is not None and severity not in SEVERITIES:
        problems.append(f"severity must be one of {', '.join(SEVERITIES)}.")
    return problems


BUG_SCHEMA = RecordSchema(
    prefix="BUG",
    directory="bugs",
    statuses=frozenset(CLASSIFICATIONS),
    required=("title", "environment", "found_by"),
    references={
        "evidence": ("EVD",),
        "execution": ("EXEC",),
        "requirements": ("REQ",),
        "cases": ("TC",),
    },
    text_lists=("steps",),
    extra_checks=(check_bug,),
)
