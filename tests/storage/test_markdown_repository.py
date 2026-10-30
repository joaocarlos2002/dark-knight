from datetime import timedelta
from pathlib import Path

import pytest

from qa_workbench.storage import repository as repository_module
from qa_workbench.storage.errors import (
    FrontmatterError,
    ImmutableFieldError,
    RecordNotFoundError,
    RecordValidationError,
    StorageError,
)
from qa_workbench.storage.frontmatter import parse_document
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema

TEST_CASES = RecordSchema(
    prefix="TC",
    directory="test-cases",
    statuses=frozenset({"draft", "active", "retired"}),
    required=("title",),
    optional_timestamps=("reviewed_at",),
    references={"requirements": ("REQ",)},
)
REQUIREMENTS = RecordSchema(
    prefix="REQ", directory="requirements", statuses=frozenset({"open", "closed"})
)


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [TEST_CASES, REQUIREMENTS])


def _create(repo: MarkdownRepository, title: str = "Login", **extra: object):
    return repo.create("TC", {"title": title, "status": "active", **extra}, "# Body\n")


def test_create_writes_a_markdown_file_with_frontmatter(
    repo: MarkdownRepository,
) -> None:
    record = _create(repo, requirements=["REQ-001"])

    assert record.id == "TC-001"
    assert record.path == repo.root / "test-cases" / "TC-001.md"
    text = record.path.read_text(encoding="utf-8")
    assert text.startswith("---\nid: TC-001\ntitle: Login\nstatus: active\n")
    assert "requirements: [REQ-001]\n" in text
    assert text.endswith("---\n\n# Body\n")


def test_timestamps_are_iso_8601_with_a_timezone_and_unquoted(
    repo: MarkdownRepository,
) -> None:
    record = _create(repo)

    document = parse_document(record.path.read_text(encoding="utf-8"))
    assert document.metadata["created_at"].utcoffset() is not None
    assert document.metadata["created_at"] == document.metadata["updated_at"]
    line = next(
        ln
        for ln in record.path.read_text(encoding="utf-8").splitlines()
        if ln.startswith("created_at:")
    )
    assert "'" not in line
    assert "T" in line


def test_ids_increase_per_prefix_and_are_never_reused(
    repo: MarkdownRepository,
) -> None:
    first = _create(repo)
    second = _create(repo)
    first.path.unlink()
    third = _create(repo)
    requirement = repo.create("REQ", {"status": "open"})

    assert [first.id, second.id, third.id] == ["TC-001", "TC-002", "TC-003"]
    assert requirement.id == "REQ-001"


def test_get_returns_what_was_created(repo: MarkdownRepository) -> None:
    created = _create(repo, tags=["login"])

    loaded = repo.get(created.id)

    assert loaded.metadata == created.metadata
    assert loaded.body == "# Body\n"


def test_managed_fields_cannot_be_chosen_when_creating(
    repo: MarkdownRepository,
) -> None:
    with pytest.raises(ValueError, match="id, created_at are managed"):
        repo.create("TC", {"id": "TC-099", "created_at": 1, "title": "x"})


def test_invalid_input_is_rejected_and_nothing_is_written(
    repo: MarkdownRepository,
) -> None:
    with pytest.raises(RecordValidationError) as error:
        repo.create("TC", {"status": "bogus", "requirements": ["TC-001"]})

    problems = "\n".join(error.value.problems)
    assert "title is required." in problems
    assert "status 'bogus' is not allowed" in problems
    assert "requirements must reference REQ ids" in problems
    assert not (repo.root / "test-cases").exists()


def test_validation_errors_name_the_file(repo: MarkdownRepository) -> None:
    with pytest.raises(RecordValidationError) as error:
        repo.create("TC", {"title": "x", "status": "nope"})

    assert "TC-001.md" in str(error.value)


def test_broken_relative_links_are_rejected_on_create(
    repo: MarkdownRepository,
) -> None:
    with pytest.raises(RecordValidationError, match="points to a missing file"):
        repo.create("TC", {"title": "x", "status": "draft"}, "[req](../x/REQ-9.md)")


def test_valid_relative_links_between_records_are_accepted(
    repo: MarkdownRepository,
) -> None:
    requirement = repo.create("REQ", {"status": "open"})

    record = repo.create(
        "TC",
        {"title": "x", "status": "draft"},
        "Covers [REQ-001](../requirements/REQ-001.md).",
    )

    assert requirement.path.exists()
    assert repo.get(record.id).body.startswith("Covers [REQ-001]")


def test_unknown_prefix_is_a_clear_error(repo: MarkdownRepository) -> None:
    with pytest.raises(ValueError, match="No schema is registered for prefix 'BUG'"):
        repo.create("BUG", {})


def test_duplicate_schemas_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Duplicate schema for prefix TC"):
        MarkdownRepository(tmp_path, [TEST_CASES, TEST_CASES])


@pytest.mark.parametrize("record_id", ["TC-404", "nope", "../escape", "BUG-001", ""])
def test_unknown_or_malformed_ids_are_not_found(
    repo: MarkdownRepository, record_id: str
) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.get(record_id)


def test_update_changes_fields_and_body_and_bumps_updated_at(
    repo: MarkdownRepository,
) -> None:
    created = _create(repo)

    updated = repo.update(created.id, {"status": "retired"}, "# New\n")

    assert updated.metadata["status"] == "retired"
    assert updated.metadata["created_at"] == created.metadata["created_at"]
    assert updated.metadata["updated_at"] >= created.metadata["updated_at"]
    reloaded = repo.get(created.id)
    assert reloaded.metadata == updated.metadata
    assert reloaded.body == "# New\n"


def test_update_without_a_body_keeps_the_body(repo: MarkdownRepository) -> None:
    created = _create(repo)

    assert repo.update(created.id, {"title": "Renamed"}).body == created.body


def test_update_keeps_field_order(repo: MarkdownRepository) -> None:
    created = _create(repo)

    repo.update(created.id, {"status": "retired"})

    text = created.path.read_text(encoding="utf-8")
    assert text.index("id:") < text.index("title:") < text.index("status:")
    assert text.index("status:") < text.index("created_at:")


def test_the_id_cannot_change(repo: MarkdownRepository) -> None:
    created = _create(repo)

    with pytest.raises(ImmutableFieldError, match="id of TC-001 is immutable"):
        repo.update(created.id, {"id": "TC-002"})

    assert repo.get(created.id).id == "TC-001"


def test_created_at_cannot_change(repo: MarkdownRepository) -> None:
    created = _create(repo)
    other = created.metadata["created_at"] - timedelta(days=1)

    with pytest.raises(ImmutableFieldError, match="created_at"):
        repo.update(created.id, {"created_at": other})


def test_passing_the_same_id_or_created_at_is_harmless(
    repo: MarkdownRepository,
) -> None:
    created = _create(repo)

    updated = repo.update(
        created.id,
        {"id": created.id, "created_at": created.metadata["created_at"], "title": "y"},
    )

    assert updated.metadata["title"] == "y"


def test_updated_at_is_managed_by_the_repository(repo: MarkdownRepository) -> None:
    created = _create(repo)

    with pytest.raises(ValueError, match="updated_at is managed"):
        repo.update(created.id, {"updated_at": created.metadata["updated_at"]})


def test_an_invalid_update_leaves_the_file_untouched(
    repo: MarkdownRepository,
) -> None:
    created = _create(repo)
    before = created.path.read_text(encoding="utf-8")

    with pytest.raises(RecordValidationError, match="status 'bogus'"):
        repo.update(created.id, {"status": "bogus"})

    assert created.path.read_text(encoding="utf-8") == before


def test_updating_a_missing_record_fails(repo: MarkdownRepository) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.update("TC-001", {"title": "x"})


def test_list_returns_records_ordered_by_id_and_can_filter_by_status(
    repo: MarkdownRepository,
) -> None:
    _create(repo, "A")
    _create(repo, "B")
    repo.update("TC-002", {"status": "retired"})

    everything = repo.list_records("TC")
    retired = repo.list_records("TC", status="retired")

    assert [r.id for r in everything.records] == ["TC-001", "TC-002"]
    assert [r.id for r in retired.records] == ["TC-002"]


def test_list_on_an_empty_repository_is_empty(repo: MarkdownRepository) -> None:
    listing = repo.list_records("TC")

    assert listing.records == ()
    assert listing.errors == ()


def test_list_reports_damaged_records_instead_of_hiding_them(
    repo: MarkdownRepository,
) -> None:
    good = _create(repo, "Good")
    bad = _create(repo, "Bad")
    bad.path.write_text("not a record", encoding="utf-8")

    listing = repo.list_records("TC")

    assert [r.id for r in listing.records] == [good.id]
    assert len(listing.errors) == 1
    assert isinstance(listing.errors[0], FrontmatterError)
    assert str(bad.path) in str(listing.errors[0])


def test_list_ignores_unrelated_files(repo: MarkdownRepository) -> None:
    _create(repo)
    (repo.root / "test-cases" / "notes.md").write_text("x", encoding="utf-8")
    (repo.root / "test-cases" / "REQ-001.md").write_text("x", encoding="utf-8")

    listing = repo.list_records("TC")

    assert len(listing.records) == 1
    assert listing.errors == ()


def test_a_hand_edited_record_is_validated_when_read(
    repo: MarkdownRepository,
) -> None:
    created = _create(repo)
    text = created.path.read_text(encoding="utf-8")
    created.path.write_text(text.replace("status: active", "status: wat"), "utf-8")

    with pytest.raises(RecordValidationError, match="status 'wat'"):
        repo.get(created.id)


def test_a_file_whose_id_does_not_match_its_name_is_rejected(
    repo: MarkdownRepository,
) -> None:
    first = _create(repo)
    second = _create(repo)
    second.path.write_text(first.path.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(RecordValidationError, match="does not match its file name"):
        repo.get(second.id)


def test_a_record_that_became_dangling_is_reported_when_read(
    repo: MarkdownRepository,
) -> None:
    requirement = repo.create("REQ", {"status": "open"})
    record = repo.create(
        "TC", {"title": "x", "status": "draft"}, "[r](../requirements/REQ-001.md)"
    )
    requirement.path.unlink()

    with pytest.raises(RecordValidationError, match="points to a missing file"):
        repo.get(record.id)


def test_write_failures_are_reported_with_the_path(
    repo: MarkdownRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path, text: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(repository_module, "write_text_atomic", broken)

    with pytest.raises(StorageError, match="Cannot write .*TC-001.md: disk full") as e:
        _create(repo)

    assert isinstance(e.value.__cause__, OSError)


def test_unserializable_values_are_reported_with_the_path(
    repo: MarkdownRepository,
) -> None:
    with pytest.raises(FrontmatterError, match="cannot be serialized") as error:
        repo.create("TC", {"title": "x", "status": "draft", "extra": Path("a")})

    assert "TC-001.md" in str(error.value)


def test_files_are_utf8_with_lf_endings(repo: MarkdownRepository) -> None:
    record = repo.create(
        "TC", {"title": "Atenção — ação", "status": "draft"}, "linha 1\nlinha 2"
    )

    raw = record.path.read_bytes()
    assert b"\r" not in raw
    assert "Atenção — ação" in raw.decode("utf-8")


def test_prefixes_lists_the_registered_kinds(repo: MarkdownRepository) -> None:
    assert repo.prefixes == ("REQ", "TC")


def test_record_ids_lists_files_without_reading_them(
    repo: MarkdownRepository,
) -> None:
    _create(repo)
    _create(repo)
    (repo.root / "test-cases" / "notes.md").write_text("x", encoding="utf-8")
    (repo.root / "test-cases" / "REQ-001.md").write_text("x", encoding="utf-8")
    (repo.root / "test-cases" / "TC-002.md").write_text("garbage", encoding="utf-8")

    assert repo.record_ids("TC") == ["TC-001", "TC-002"]
    assert repo.record_ids("REQ") == []


def test_path_of_points_at_the_record_file(repo: MarkdownRepository) -> None:
    assert repo.path_of("TC-007") == repo.root / "test-cases" / "TC-007.md"
    with pytest.raises(RecordNotFoundError):
        repo.path_of("BUG-001")
