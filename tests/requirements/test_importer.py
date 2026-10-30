from pathlib import Path

import pytest

from qa_workbench.requirements.importer import (
    MAX_SOURCE_BYTES,
    RequirementImportError,
    import_requirements,
)
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.storage.history import sha256_file
from qa_workbench.storage.repository import MarkdownRepository

SOURCE = """# Login requirements

## Users can log in

Priority: high
Tags: auth, login
Author: Ana

A registered user signs in.

Acceptance criteria:
- The user reaches the dashboard.
- A wrong password shows an error.

## Users can reset their password

Priority: medium
"""


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [REQUIREMENT_SCHEMA])


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "login.md"
    path.write_text(SOURCE, encoding="utf-8")
    return path


def test_requirements_are_created_as_drafts_with_their_details(
    repo: MarkdownRepository, source: Path
) -> None:
    report = import_requirements(repo, source)

    assert [r.id for r in report.created] == ["REQ-001", "REQ-002"]
    first = report.created[0].metadata
    assert first["title"] == "Users can log in"
    assert first["status"] == "draft"
    assert first["priority"] == "high"
    assert first["tags"] == ["auth", "login"]
    assert first["acceptance_criteria"] == [
        "The user reaches the dashboard.",
        "A wrong password shows an error.",
    ]
    assert report.skipped == ()
    assert report.issues == ()


def test_the_source_and_its_author_are_preserved(
    repo: MarkdownRepository, source: Path
) -> None:
    report = import_requirements(repo, source, source_version="v1.2")

    metadata = report.created[0].metadata
    assert metadata["source"] == "login.md"
    assert metadata["source_ref"] == "line 3"
    assert metadata["source_sha256"] == sha256_file(source)
    assert metadata["source_format"] == "markdown"
    assert metadata["source_version"] == "v1.2"
    assert metadata["author"] == "Ana"
    assert metadata["imported_at"].utcoffset() is not None
    assert report.created[1].metadata["source_ref"] == "line 15"


def test_the_default_author_fills_in_only_when_the_source_has_none(
    repo: MarkdownRepository, source: Path
) -> None:
    report = import_requirements(repo, source, author="Bruno")

    assert report.created[0].metadata["author"] == "Ana"
    assert report.created[1].metadata["author"] == "Bruno"


def test_optional_fields_are_left_out_when_unknown(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    path = tmp_path / "one.txt"
    path.write_text("Export reports\n", encoding="utf-8")

    metadata = import_requirements(repo, path).created[0].metadata

    assert not {"priority", "author", "tags", "source_version"} & set(metadata)
    assert metadata["source_format"] == "text"


def test_the_source_file_is_never_modified(
    repo: MarkdownRepository, source: Path
) -> None:
    before = (source.read_bytes(), source.stat().st_mtime_ns)

    import_requirements(repo, source)

    assert (source.read_bytes(), source.stat().st_mtime_ns) == before


def test_the_record_body_is_readable_markdown(
    repo: MarkdownRepository, source: Path
) -> None:
    record = import_requirements(repo, source).created[0]

    assert record.body == (
        "# Users can log in\n\n"
        "A registered user signs in.\n\n"
        "## Acceptance criteria\n\n"
        "- The user reaches the dashboard.\n"
        "- A wrong password shows an error.\n"
    )


def test_importing_the_same_file_twice_does_not_duplicate(
    repo: MarkdownRepository, source: Path
) -> None:
    import_requirements(repo, source)

    again = import_requirements(repo, source)

    assert again.created == ()
    assert again.skipped == ("REQ-001", "REQ-002")
    assert repo.record_ids("REQ") == ["REQ-001", "REQ-002"]


def test_a_changed_source_is_imported_as_new_requirements(
    repo: MarkdownRepository, source: Path
) -> None:
    import_requirements(repo, source)
    source.write_text(SOURCE + "\n## A new one\n", encoding="utf-8")

    again = import_requirements(repo, source)

    assert len(again.created) == 3
    assert again.skipped == ()


def test_problems_are_reported_and_valid_requirements_still_import(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    path = tmp_path / "mixed.md"
    path.write_text(
        "## Bad\n\nPriority: urgent\n\n## Good\n\nPriority: low\n", encoding="utf-8"
    )

    report = import_requirements(repo, path)

    assert [r.metadata["title"] for r in report.created] == ["Good"]
    assert [i.location for i in report.issues] == ["mixed.md:1"]
    assert "priority 'urgent' is not understood" in report.issues[0].message


def test_a_status_written_in_the_source_is_kept(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    path = tmp_path / "status.md"
    path.write_text("## Fine\n\nStatus: approved\n", encoding="utf-8")

    report = import_requirements(repo, path)

    assert report.created[0].metadata["status"] == "approved"


def test_a_file_with_no_requirement_fails_with_guidance(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    path = tmp_path / "prose.md"
    path.write_text("Just some prose.\n", encoding="utf-8")

    report = import_requirements(repo, path)

    assert report.created == ()
    assert report.issues[0].message.startswith("no requirement found")


@pytest.mark.parametrize(
    ("name", "content", "match"),
    [
        ("missing.md", None, "is not a file"),
        ("empty.md", b"", "is empty"),
        ("data.pdf", b"%PDF-1.4", "unsupported file type '.pdf'"),
        ("sheet.xlsx", b"PK", "unsupported file type '.xlsx'"),
        ("latin.md", "## Atenção\n".encode("latin-1"), "not valid UTF-8"),
    ],
)
def test_unreadable_sources_fail_explicitly(
    repo: MarkdownRepository,
    tmp_path: Path,
    name: str,
    content: bytes | None,
    match: str,
) -> None:
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content)

    with pytest.raises(RequirementImportError, match=match):
        import_requirements(repo, path)

    assert repo.record_ids("REQ") == []


def test_oversized_sources_are_refused(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    path = tmp_path / "big.md"
    path.write_bytes(b"## R\n" + b"x" * MAX_SOURCE_BYTES)

    with pytest.raises(RequirementImportError, match="the limit is"):
        import_requirements(repo, path)


def test_the_format_can_be_forced_for_other_extensions(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    path = tmp_path / "reqs.requirements"
    path.write_text("## From a custom extension\n", encoding="utf-8")

    with pytest.raises(RequirementImportError, match="unsupported file type"):
        import_requirements(repo, path)
    report = import_requirements(repo, path, format_name="markdown")

    assert report.created[0].metadata["title"] == "From a custom extension"


def test_imported_requirements_are_valid_records(
    repo: MarkdownRepository, source: Path
) -> None:
    import_requirements(repo, source)

    listing = repo.list_records("REQ")

    assert len(listing.records) == 2
    assert listing.errors == ()
