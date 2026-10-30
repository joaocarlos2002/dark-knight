"""Test suite records (REQ-015)."""

from collections.abc import Mapping
from typing import Any

from qa_workbench.storage.validation import RecordSchema

DRAFT = "draft"
STATUSES = frozenset({DRAFT, "active", "archived"})
TYPES = frozenset(
    {
        "smoke",
        "sanity",
        "regression",
        "end_to_end",
        "integration",
        "api",
        "functional",
        "security",
        "compatibility",
        "acceptance",
        "custom",
    }
)


def _check_cases(metadata: Mapping[str, Any]) -> list[str]:
    cases = metadata.get("cases")
    if not isinstance(cases, list):
        return []
    duplicates = sorted({c for c in cases if cases.count(c) > 1})
    if duplicates:
        return [f"cases lists the same case more than once: {', '.join(duplicates)}."]
    return []


SUITE_SCHEMA = RecordSchema(
    prefix="SUITE",
    directory="test-suites",
    statuses=STATUSES,
    required=("title", "type"),
    references={"cases": ("TC",)},
    choices={"type": TYPES},
    text_lists=("tags",),
    extra_checks=(_check_cases,),
)
