from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from qa_workbench.storage.errors import FrontmatterError
from qa_workbench.storage.frontmatter import (
    Document,
    dump_document,
    parse_document,
    read_document,
)

SPEC_EXAMPLE = """---
id: TC-001
title: "Autenticar com credenciais válidas"
status: active
priority: high
requirements: [REQ-001]
issues: []
tags: [authentication, login]
created_at: 2026-01-01T10:00:00-03:00
updated_at: 2026-01-01T10:00:00-03:00
finished_at:
---

# TC-001 — Autenticar com credenciais válidas

## Passos

1. Acessar a tela de login.
"""


def test_the_specification_example_is_parsed() -> None:
    document = parse_document(SPEC_EXAMPLE)

    assert document.metadata["id"] == "TC-001"
    assert document.metadata["title"] == "Autenticar com credenciais válidas"
    assert document.metadata["requirements"] == ["REQ-001"]
    assert document.metadata["issues"] == []
    assert document.metadata["finished_at"] is None
    assert document.body.startswith("# TC-001 — Autenticar")


def test_timestamps_keep_their_timezone() -> None:
    created = parse_document(SPEC_EXAMPLE).metadata["created_at"]

    assert isinstance(created, datetime)
    assert created.utcoffset() == timedelta(hours=-3)


def test_crlf_files_are_accepted_and_normalized() -> None:
    document = parse_document("---\r\nid: TC-001\r\n---\r\n\r\nLine 1\r\nLine 2\r\n")

    assert document.metadata == {"id": "TC-001"}
    assert document.body == "Line 1\nLine 2\n"


def test_document_without_a_body_is_valid() -> None:
    document = parse_document("---\nid: TC-001\n---\n")

    assert document == Document({"id": "TC-001"}, "")


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("# Just markdown\n", "must start with a '---'"),
        ("", "must start with a '---'"),
        ("\n---\nid: TC-001\n---\n", "must start with a '---'"),
        ("---\nid: TC-001\n", "not closed"),
        ("---\n---\n", "is empty"),
        ("---\n- a\n- b\n---\n", "must be a mapping"),
        ("---\njust text\n---\n", "must be a mapping"),
        ("---\n1: one\n---\n", "must be text"),
        ("---\nid: [unclosed\n---\n", "not valid YAML"),
        ("﻿---\nid: TC-001\n---\n", "byte order mark"),
    ],
)
def test_invalid_documents_explain_what_is_wrong(text: str, reason: str) -> None:
    with pytest.raises(FrontmatterError, match=reason):
        parse_document(text, "note.md")


def test_errors_name_the_source_file() -> None:
    with pytest.raises(FrontmatterError) as error:
        parse_document("no frontmatter", "test-cases/TC-001.md")

    assert "test-cases/TC-001.md" in str(error.value)


def test_yaml_errors_keep_their_cause() -> None:
    with pytest.raises(FrontmatterError) as error:
        parse_document("---\nid: [unclosed\n---\n")

    assert error.value.__cause__ is not None


def test_dump_matches_the_specification_style() -> None:
    created = datetime(2026, 1, 1, 10, 0, tzinfo=timezone(timedelta(hours=-3)))

    text = dump_document(
        {
            "id": "TC-001",
            "title": "Autenticar com credenciais válidas",
            "requirements": ["REQ-001"],
            "issues": [],
            "created_at": created,
            "finished_at": None,
        },
        "# TC-001\n",
    )

    assert text == (
        "---\n"
        "id: TC-001\n"
        "title: Autenticar com credenciais válidas\n"
        "requirements: [REQ-001]\n"
        "issues: []\n"
        "created_at: 2026-01-01T10:00:00-03:00\n"
        "finished_at: null\n"
        "---\n"
        "\n"
        "# TC-001\n"
    )


def test_roundtrip_preserves_metadata_order_types_and_body() -> None:
    original = parse_document(SPEC_EXAMPLE)

    again = parse_document(dump_document(original.metadata, original.body))

    assert again == original
    assert list(again.metadata) == list(original.metadata)


def test_dump_never_emits_a_timestamp_as_a_quoted_string() -> None:
    stamp = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)

    text = dump_document({"created_at": stamp}, "")

    assert "created_at: 2026-01-01T10:00:00+00:00\n" in text
    assert "'" not in text


def test_text_that_looks_like_a_date_stays_text() -> None:
    text = dump_document({"title": "2026-01-01", "day": date(2026, 1, 2)}, "")
    document = parse_document(text)

    assert document.metadata["title"] == "2026-01-01"
    assert document.metadata["day"] == date(2026, 1, 2)


def test_long_titles_are_not_wrapped() -> None:
    title = "word " * 60

    document = parse_document(dump_document({"title": title.strip()}, ""))

    assert document.metadata["title"] == title.strip()


def test_dump_normalizes_body_line_endings_and_final_newline() -> None:
    text = dump_document({"id": "TC-001"}, "a\r\nb\r\n\r\n\r\n")

    assert text.endswith("\n\na\nb\n")


def test_unserializable_metadata_is_reported() -> None:
    with pytest.raises(FrontmatterError, match="cannot be serialized"):
        dump_document({"path": Path("x")}, "")


def test_read_document_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "TC-001.md"
    path.write_text(SPEC_EXAMPLE, encoding="utf-8")

    assert read_document(path).metadata["id"] == "TC-001"


def test_read_document_rejects_files_that_are_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "TC-001.md"
    path.write_bytes("---\nid: TC-001\ntitle: Atenção\n---\n".encode("latin-1"))

    with pytest.raises(FrontmatterError, match="not valid UTF-8") as error:
        read_document(path)

    assert str(path) in str(error.value)


def test_read_document_reports_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FrontmatterError, match="cannot be read"):
        read_document(tmp_path / "missing.md")
