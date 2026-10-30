"""Test case records (REQ-011, REQ-012)."""

from collections.abc import Mapping
from typing import Any

from qa_workbench.core.secrets import find_secrets
from qa_workbench.storage.validation import RecordSchema
from qa_workbench.testcases.techniques import (
    TECHNIQUE_NAMES,
    Technique,
    parse_technique,
)

DRAFT = "draft"
STATUSES = frozenset({DRAFT, "in_review", "active", "deprecated"})
PRIORITIES = frozenset({"high", "medium", "low"})
CRITICALITIES = frozenset({"critical", "major", "minor", "trivial"})
TYPES = frozenset(
    {
        "functional",
        "regression",
        "smoke",
        "sanity",
        "integration",
        "end_to_end",
        "api",
        "security",
        "performance",
        "usability",
        "accessibility",
        "compatibility",
        "acceptance",
        "exploratory",
    }
)
ORIGINS = frozenset({"manual", "imported", "ai"})

_TEXT_FIELDS = ("title", "objective", "expected_result", "profile")
_TEXT_LIST_FIELDS = ("preconditions", "test_data")


def _is_exploratory(metadata: Mapping[str, Any]) -> bool:
    techniques = metadata.get("techniques") or []
    return isinstance(techniques, list) and Technique.EXPLORATORY.value in techniques


def _check_steps(metadata: Mapping[str, Any], problems: list[str]) -> None:
    steps = metadata.get("steps")
    if steps is None:
        steps = []
    if not isinstance(steps, list):
        problems.append("steps must be a list.")
        return
    for number, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            problems.append(
                f"step {number} must have an action and an expected result."
            )
            continue
        action = step.get("action")
        if not isinstance(action, str) or not action.strip():
            problems.append(f"step {number} needs an action.")
        expected = step.get("expected", "")
        if expected is not None and not isinstance(expected, str):
            problems.append(f"step {number}: expected must be text.")
        extra = set(step) - {"action", "expected"}
        if extra:
            problems.append(f"step {number} has unknown fields: {sorted(extra)}.")
    if not _is_exploratory(metadata):
        if not steps:
            problems.append("a test case needs at least one step (except exploratory).")
        if not str(metadata.get("expected_result") or "").strip():
            problems.append("expected_result is required (except exploratory).")


def _check_techniques(metadata: Mapping[str, Any], problems: list[str]) -> None:
    techniques = metadata.get("techniques") or []
    if not isinstance(techniques, list):
        return  # reported by the text_lists check
    for name in techniques:
        if name not in TECHNIQUE_NAMES:
            problems.append(
                f"technique {name!r} is not supported; use one of: "
                f"{', '.join(TECHNIQUE_NAMES)}."
            )
    data = metadata.get("technique_data")
    if data is None:
        return
    if not isinstance(data, dict):
        problems.append("technique_data must map technique names to their data.")
        return
    for name, content in data.items():
        if name not in techniques:
            problems.append(f"technique_data has {name!r}, which is not in techniques.")
            continue
        try:
            parse_technique(name, content)
        except ValueError as error:
            problems.append(f"technique_data {error}")


def _check_secrets(metadata: Mapping[str, Any], problems: list[str]) -> None:
    texts: list[tuple[str, str]] = [
        (name, str(metadata[name])) for name in _TEXT_FIELDS if metadata.get(name)
    ]
    for name in _TEXT_LIST_FIELDS:
        value = metadata.get(name)
        if isinstance(value, list):
            texts += [(f"{name}[{i}]", str(item)) for i, item in enumerate(value, 1)]
    steps = metadata.get("steps")
    if isinstance(steps, list):
        for number, step in enumerate(steps, start=1):
            if isinstance(step, dict):
                texts += [
                    (f"step {number} {key}", str(step[key]))
                    for key in ("action", "expected")
                    if step.get(key)
                ]
    for where, text in texts:
        for description in find_secrets(text):
            problems.append(
                f"{where} contains {description}; reference it by name instead, "
                "for example $TEST_PASSWORD."
            )


def check_test_case(metadata: Mapping[str, Any]) -> list[str]:
    """Rules of a test case that a schema cannot express declaratively."""
    problems: list[str] = []
    _check_steps(metadata, problems)
    _check_techniques(metadata, problems)
    _check_secrets(metadata, problems)
    return problems


TEST_CASE_SCHEMA = RecordSchema(
    prefix="TC",
    directory="test-cases",
    statuses=STATUSES,
    required=("title", "objective", "priority", "type", "origin"),
    references={
        "requirements": ("REQ",),
        "issues": ("ISSUE",),
        "suites": ("SUITE",),
    },
    choices={
        "priority": PRIORITIES,
        "criticality": CRITICALITIES,
        "type": TYPES,
        "origin": ORIGINS,
    },
    text_lists=(
        "preconditions",
        "test_data",
        "environments",
        "tags",
        "techniques",
    ),
    extra_checks=(check_test_case,),
)
