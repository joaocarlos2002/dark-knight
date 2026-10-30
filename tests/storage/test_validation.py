from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from qa_workbench.storage.validation import (
    RecordSchema,
    validate_links,
    validate_metadata,
)

NOW = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

SCHEMA = RecordSchema(
    prefix="TC",
    directory="test-cases",
    statuses=frozenset({"draft", "active", "retired"}),
    required=("title",),
    optional_timestamps=("reviewed_at",),
    references={"requirements": ("REQ",), "suite": ("SUITE",)},
)


def _metadata(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": "TC-001",
        "title": "Login",
        "status": "active",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return values


def _problems(**overrides: Any) -> list[str]:
    return validate_metadata(SCHEMA, _metadata(**overrides))


def test_a_complete_record_has_no_problems() -> None:
    assert _problems() == []


def test_unknown_extra_fields_are_allowed() -> None:
    assert _problems(tags=["login"], provider="github", external_id="42") == []


def test_missing_required_fields_are_all_reported() -> None:
    problems = validate_metadata(SCHEMA, {})

    assert problems == [
        "id is required.",
        "status is required.",
        "created_at is required.",
        "updated_at is required.",
        "title is required.",
    ]


def test_blank_required_text_counts_as_missing() -> None:
    assert "title is required." in _problems(title="   ")
    assert "title is required." in _problems(title=None)


def test_all_problems_are_reported_together() -> None:
    problems = _problems(status="bogus", id="TC-1", created_at="today")

    assert len(problems) >= 3


@pytest.mark.parametrize("value", ["TC-1", "TC-0001", "tc-001", "nope", ""])
def test_malformed_ids_are_rejected(value: str) -> None:
    assert any(p.startswith("id") for p in _problems(id=value))


def test_id_prefix_must_match_the_schema() -> None:
    assert "id must start with TC-, got REQ-001." in _problems(id="REQ-001")


def test_id_must_match_the_file_name() -> None:
    problems = validate_metadata(SCHEMA, _metadata(), expected_id="TC-002")

    assert "id TC-001 does not match its file name TC-002." in problems


def test_non_text_id_is_rejected() -> None:
    assert "id must be text, got int 1." in _problems(id=1)


def test_status_must_be_one_of_the_schema_values() -> None:
    problems = _problems(status="Active")

    assert problems == [
        "status 'Active' is not allowed; use one of: active, draft, retired."
    ]


@pytest.mark.parametrize(
    ("value", "fragment"),
    [
        (datetime(2026, 1, 1, 10, 0), "a timestamp without a timezone"),
        (date(2026, 1, 1), "a date without a time or timezone"),
        ("2026-01-01T10:00:00-03:00", "written without quotes"),
        (12345, "int 12345"),
    ],
)
def test_timestamps_need_an_iso_8601_timezone(value: Any, fragment: str) -> None:
    problems = _problems(created_at=value, updated_at=value)

    assert any("created_at must be an ISO 8601 timestamp" in p for p in problems)
    assert any(fragment in p for p in problems)


def test_any_timezone_offset_is_accepted() -> None:
    stamp = datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=-3)))

    assert _problems(created_at=stamp, updated_at=stamp) == []


def test_updated_at_cannot_precede_created_at() -> None:
    problems = _problems(updated_at=NOW - timedelta(seconds=1))

    assert problems == ["updated_at cannot be earlier than created_at."]


def test_optional_timestamps_may_be_empty_but_must_be_valid_when_set() -> None:
    assert _problems(reviewed_at=None) == []
    assert _problems(reviewed_at=NOW) == []
    assert any("reviewed_at must be" in p for p in _problems(reviewed_at="soon"))


def test_references_accept_one_id_or_a_list() -> None:
    assert _problems(requirements=["REQ-001", "REQ-002"], suite="SUITE-001") == []
    assert _problems(requirements=[]) == []
    assert _problems(requirements=None) == []


def test_references_must_have_an_allowed_prefix() -> None:
    problems = _problems(requirements=["REQ-001", "TC-002"])

    assert problems == ["requirements must reference REQ ids, got TC-002."]


def test_malformed_references_are_explained() -> None:
    problems = _problems(requirements=["REQ-1", 7])

    assert any(p.startswith("requirements: 'REQ-1' is not canonical") for p in problems)
    assert "requirements must contain ids, got int 7." in problems


def test_schema_rejects_bad_definitions() -> None:
    with pytest.raises(ValueError, match="Unknown id prefix"):
        RecordSchema("NOPE", "x", frozenset({"a"}))
    with pytest.raises(ValueError, match="relative folder"):
        RecordSchema("TC", "../escape", frozenset({"a"}))
    with pytest.raises(ValueError, match="relative folder"):
        RecordSchema("TC", "/abs", frozenset({"a"}))
    with pytest.raises(ValueError, match="at least one status"):
        RecordSchema("TC", "x", frozenset())
    with pytest.raises(ValueError, match="unknown prefixes"):
        RecordSchema("TC", "x", frozenset({"a"}), references={"f": ("NOPE",)})


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "test-cases").mkdir()
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "REQ-001.md").write_text("x", encoding="utf-8")
    (tmp_path / "notes with space.md").write_text("x", encoding="utf-8")
    return tmp_path


def _link_problems(project: Path, body: str) -> list[str]:
    document = project / "test-cases" / "TC-001.md"
    return validate_links(body, document=document, root=project)


def test_relative_links_to_existing_files_are_valid(project: Path) -> None:
    body = (
        "See [req](../requirements/REQ-001.md) and ![img](../notes%20with%20space.md)."
    )

    assert _link_problems(project, body) == []


def test_fragments_and_queries_are_ignored_when_resolving(project: Path) -> None:
    assert _link_problems(project, "[a](../requirements/REQ-001.md#section)") == []
    assert _link_problems(project, "[a](../requirements/REQ-001.md?x=1)") == []


def test_links_with_titles_are_understood(project: Path) -> None:
    assert _link_problems(project, '[a](../requirements/REQ-001.md "Title")') == []


def test_external_links_and_anchors_are_not_checked(project: Path) -> None:
    body = "[a](https://example.com) [b](http://x.test) [c](mailto:a@b.c) [d](#top)"

    assert _link_problems(project, body) == []


def test_missing_targets_are_reported_with_the_line(project: Path) -> None:
    problems = _link_problems(project, "ok\n\n[gone](../requirements/REQ-999.md)")

    assert problems == [
        "line 3: link '../requirements/REQ-999.md' points to a missing file."
    ]


@pytest.mark.parametrize(
    "target",
    ["/etc/passwd", "\\server\\share", "C:\\Users\\x.md", "file:///x.md", "C:/x.md"],
)
def test_absolute_links_are_rejected(project: Path, target: str) -> None:
    problems = _link_problems(project, f"[a]({target})")

    assert len(problems) == 1
    assert "is absolute; use a relative path" in problems[0]


def test_links_cannot_escape_the_project_folder(project: Path) -> None:
    problems = _link_problems(project, "[a](../../outside.md)")

    assert problems == [
        "line 1: link '../../outside.md' points outside the project folder."
    ]


def test_links_inside_code_are_ignored(project: Path) -> None:
    body = "`[a](missing.md)`\n\n```\n[b](missing.md)\n```\n\n~~~\n[c](missing.md)\n~~~"

    assert _link_problems(project, body) == []


def test_wikilinks_are_allowed_but_not_checked(project: Path) -> None:
    assert _link_problems(project, "See [[Some Note]] and [[REQ-001|req]]") == []


def test_every_broken_link_is_reported(project: Path) -> None:
    problems = _link_problems(project, "[a](x.md) [b](y.md)")

    assert len(problems) == 2
