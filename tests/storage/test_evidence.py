import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qa_workbench.storage.errors import (
    EvidenceError,
    RecordFinalizedError,
    RecordNotFoundError,
    RecordValidationError,
)
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.history import sha256_file
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema

TEST_CASES = RecordSchema(
    prefix="TC", directory="test-cases", statuses=frozenset({"draft"})
)
PNG = b"\x89PNG\r\n\x1a\n" + b"fake image bytes" * 10


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [EVIDENCE_SCHEMA, TEST_CASES])


@pytest.fixture
def store(repo: MarkdownRepository) -> EvidenceStore:
    return EvidenceStore(repo)


@pytest.fixture
def screenshot(tmp_path: Path) -> Path:
    path = tmp_path / "capture" / "login.png"
    path.parent.mkdir()
    path.write_bytes(PNG)
    return path


def _register(store: EvidenceStore, file: Path, **extra: object):
    return store.register(
        file, source="playwright", description="Login page after submit", **extra
    )


def test_the_store_needs_the_evidence_schema(tmp_path: Path) -> None:
    repo = MarkdownRepository(tmp_path, [TEST_CASES])

    with pytest.raises(ValueError, match="no EVD schema"):
        EvidenceStore(repo)


def test_registering_copies_the_file_and_records_its_hash(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    record = _register(store, screenshot, step="3", execution="EXEC-001")

    metadata = record.metadata
    assert record.id == "EVD-001"
    assert metadata["file"] == "evidence/files/EVD-001/login.png"
    assert metadata["original_name"] == "login.png"
    assert metadata["sha256"] == sha256_file(screenshot)
    assert metadata["size"] == len(PNG)
    assert metadata["media_type"] == "image/png"
    assert metadata["source"] == "playwright"
    assert metadata["description"] == "Login page after submit"
    assert metadata["step"] == "3"
    assert metadata["execution"] == "EXEC-001"
    assert (repo.root / metadata["file"]).read_bytes() == PNG


def test_the_original_file_is_preserved(store: EvidenceStore, screenshot: Path) -> None:
    before = screenshot.stat().st_mtime_ns

    _register(store, screenshot)

    assert screenshot.read_bytes() == PNG
    assert screenshot.stat().st_mtime_ns == before


def test_unknown_types_get_a_generic_media_type(
    store: EvidenceStore, tmp_path: Path
) -> None:
    path = tmp_path / "trace.zipx9"
    path.write_bytes(b"data")

    assert _register(store, path).metadata["media_type"] == "application/octet-stream"


def test_each_registration_gets_its_own_folder(
    store: EvidenceStore, screenshot: Path
) -> None:
    first = _register(store, screenshot)
    second = _register(store, screenshot)

    assert (first.id, second.id) == ("EVD-001", "EVD-002")
    assert first.metadata["file"] != second.metadata["file"]
    assert store.verify_all() == {}


def test_unsafe_file_names_are_sanitized(store: EvidenceStore, tmp_path: Path) -> None:
    path = tmp_path / "we ird name.png"
    path.write_bytes(PNG)

    record = _register(store, path)

    assert record.metadata["file"] == "evidence/files/EVD-001/we ird name.png"


def test_characters_outside_the_safe_set_are_replaced(
    store: EvidenceStore, tmp_path: Path
) -> None:
    path = tmp_path / "café #1.png"
    path.write_bytes(PNG)

    record = _register(store, path)

    assert record.metadata["file"] == "evidence/files/EVD-001/caf_ _1.png"
    assert record.metadata["original_name"] == "café #1.png"


def test_evidence_records_cannot_be_edited(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    record = _register(store, screenshot)

    with pytest.raises(RecordFinalizedError):
        repo.update(record.id, {"sha256": "0" * 64})


def test_corrections_to_evidence_are_history_events(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    record = _register(store, screenshot)

    repo.add_history_event(
        record.id, "correction", "Ana", "Wrong step number.", {"step": "4"}
    )

    assert store.verify(record.id) == []


def test_intact_evidence_verifies_clean(store: EvidenceStore, screenshot: Path) -> None:
    record = _register(store, screenshot)

    assert store.verify(record.id) == []
    assert store.verify_all() == {}


def test_a_modified_file_is_detected(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    record = _register(store, screenshot)
    (repo.root / record.metadata["file"]).write_bytes(PNG[:-1] + b"X")

    problems = store.verify(record.id)

    assert problems == ["the file content does not match its recorded SHA-256."]


def test_a_truncated_file_reports_size_and_hash(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    record = _register(store, screenshot)
    (repo.root / record.metadata["file"]).write_bytes(PNG[:10])

    problems = store.verify(record.id)

    assert f"the file size is 10 bytes, but {len(PNG)} were recorded." in problems
    assert any("SHA-256" in p for p in problems)


def test_a_missing_file_is_detected(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    record = _register(store, screenshot)
    (repo.root / record.metadata["file"]).unlink()

    assert store.verify(record.id) == ["the evidence file login.png is missing."]


def test_hand_editing_the_record_is_detected(
    store: EvidenceStore, screenshot: Path
) -> None:
    record = _register(store, screenshot)
    record.path.write_text(
        record.path.read_text(encoding="utf-8").replace(
            record.metadata["sha256"], "0" * 64
        ),
        encoding="utf-8",
    )

    problems = store.verify(record.id)

    assert any("modified after it was finalized" in p for p in problems)
    assert any("does not match its recorded SHA-256" in p for p in problems)


def test_a_path_that_leaves_the_project_is_refused(
    store: EvidenceStore, screenshot: Path
) -> None:
    record = _register(store, screenshot)
    record.path.write_text(
        record.path.read_text(encoding="utf-8").replace(
            "evidence/files/EVD-001/login.png", "../../capture/login.png"
        ),
        encoding="utf-8",
    )

    problems = store.verify(record.id)

    assert any("points outside the project folder" in p for p in problems)


def test_verify_all_lists_only_damaged_evidence(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    good = _register(store, screenshot)
    bad = _register(store, screenshot)
    (repo.root / bad.metadata["file"]).write_bytes(b"changed")

    assert list(store.verify_all()) == [bad.id]
    assert store.verify(good.id) == []


def test_an_annotated_version_is_a_separate_file_pointing_at_the_original(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path, tmp_path: Path
) -> None:
    original = _register(store, screenshot)
    annotated_file = tmp_path / "login-annotated.png"
    annotated_file.write_bytes(PNG + b"arrow")

    annotated = _register(store, annotated_file, derived_from=original.id)

    assert annotated.metadata["derived_from"] == original.id
    assert annotated.metadata["sha256"] != original.metadata["sha256"]
    assert annotated.metadata["file"] != original.metadata["file"]
    assert (repo.root / original.metadata["file"]).read_bytes() == PNG
    assert store.verify_all() == {}


def test_derived_from_must_exist(store: EvidenceStore, screenshot: Path) -> None:
    with pytest.raises(RecordNotFoundError):
        _register(store, screenshot, derived_from="EVD-099")

    assert store.verify_all() == {}


def test_derived_from_must_be_evidence(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    repo.create("TC", {"status": "draft"})

    with pytest.raises(EvidenceError, match="TC-001 is not an evidence record"):
        _register(store, screenshot, derived_from="TC-001")


def test_a_path_that_is_not_a_file_is_refused(
    store: EvidenceStore, tmp_path: Path
) -> None:
    with pytest.raises(EvidenceError, match="is not a file"):
        _register(store, tmp_path / "missing.png")
    with pytest.raises(EvidenceError, match="is not a file"):
        _register(store, tmp_path)


@pytest.mark.parametrize(
    ("source", "description", "match"),
    [(" ", "x", "needs a source"), ("x", " ", "needs a description")],
)
def test_source_and_description_are_required(
    store: EvidenceStore, screenshot: Path, source: str, description: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        store.register(screenshot, source=source, description=description)


@pytest.mark.parametrize("url", ["ftp://x.test/a", "not a url", "https://"])
def test_the_source_url_must_be_http(
    store: EvidenceStore, screenshot: Path, url: str
) -> None:
    with pytest.raises(ValueError, match="source_url must be an http"):
        _register(store, screenshot, source_url=url)


def test_a_valid_source_url_and_capture_time_are_kept(
    store: EvidenceStore, screenshot: Path
) -> None:
    moment = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    url = "https://staging.example.com/login"

    record = _register(store, screenshot, source_url=url, captured_at=moment)

    assert record.metadata["source_url"] == url
    assert record.metadata["captured_at"] == moment


def test_optional_fields_are_omitted_when_not_given(
    store: EvidenceStore, screenshot: Path
) -> None:
    record = _register(store, screenshot)

    optional = {"step", "execution", "source_url", "derived_from"}
    assert not optional & set(record.metadata)


def test_a_failed_registration_leaves_nothing_behind(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    with pytest.raises(RecordValidationError, match="execution must reference EXEC"):
        _register(store, screenshot, execution="TC-001")

    assert not (repo.root / "evidence" / "files").exists() or not any(
        (repo.root / "evidence" / "files").iterdir()
    )
    assert repo.record_ids("EVD") == []


def test_a_corrupted_copy_is_never_registered(
    store: EvidenceStore,
    repo: MarkdownRepository,
    screenshot: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bad_copy(source: Path, destination: Path) -> Path:
        Path(destination).write_bytes(b"corrupted")
        return Path(destination)

    monkeypatch.setattr(shutil, "copyfile", bad_copy)

    with pytest.raises(EvidenceError, match="does not match the original"):
        _register(store, screenshot)

    assert not (repo.root / "evidence" / "files" / "EVD-001").exists()
    assert repo.record_ids("EVD") == []


def test_a_leftover_folder_is_reported(
    store: EvidenceStore, repo: MarkdownRepository, screenshot: Path
) -> None:
    (repo.root / "evidence" / "files" / "EVD-001").mkdir(parents=True)

    with pytest.raises(EvidenceError, match="already exists"):
        _register(store, screenshot)
