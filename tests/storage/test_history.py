from datetime import UTC, datetime
from pathlib import Path

import pytest

from qa_workbench.storage.errors import HistoryError, StorageError
from qa_workbench.storage.history import (
    GENESIS,
    HistoryStore,
    history_path,
    sha256_file,
)


@pytest.fixture
def record(tmp_path: Path) -> Path:
    path = tmp_path / "EXEC-001.md"
    path.write_text("---\nid: EXEC-001\nstatus: finalized\n---\n\nBody\n", "utf-8")
    return path


@pytest.fixture
def store(record: Path) -> HistoryStore:
    return HistoryStore(lambda record_id: record.with_name(f"{record_id}.md"))


def test_history_lives_next_to_the_record(record: Path) -> None:
    assert history_path(record) == record.with_name("EXEC-001.history.md")


def test_sha256_matches_a_known_value(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_bytes(b"abc")

    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sealing_records_the_hash_of_the_record(
    store: HistoryStore, record: Path
) -> None:
    event = store.seal("EXEC-001")

    assert event.sequence == 1
    assert event.kind == "sealed"
    assert event.author == "qa-workbench"
    assert event.previous_hash == GENESIS
    assert event.details == {"record_sha256": sha256_file(record)}
    assert event.timestamp.utcoffset() is not None
    assert store.is_sealed("EXEC-001")


def test_a_sealed_record_verifies_clean(store: HistoryStore) -> None:
    store.seal("EXEC-001")

    assert store.verify("EXEC-001") == []


def test_sealing_twice_is_refused(store: HistoryStore) -> None:
    store.seal("EXEC-001")

    with pytest.raises(HistoryError, match="already sealed"):
        store.seal("EXEC-001")


def test_sealing_a_missing_record_is_refused(tmp_path: Path) -> None:
    store = HistoryStore(lambda record_id: tmp_path / f"{record_id}.md")

    with pytest.raises(HistoryError, match="does not exist"):
        store.seal("EXEC-001")


def test_corrections_and_additions_are_appended_with_a_chain(
    store: HistoryStore,
) -> None:
    seal = store.seal("EXEC-001")

    correction = store.append(
        "EXEC-001",
        "correction",
        "Ana",
        "Wrong environment recorded.",
        {"environment": "staging"},
    )
    addition = store.append("EXEC-001", "addition", "Bruno", "Linked the bug.")

    assert [e.sequence for e in (seal, correction, addition)] == [1, 2, 3]
    assert correction.previous_hash == seal.hash
    assert addition.previous_hash == correction.hash
    assert correction.details == {"environment": "staging"}
    assert store.verify("EXEC-001") == []


def test_events_roundtrip_through_the_file(store: HistoryStore) -> None:
    store.seal("EXEC-001")
    written = store.append(
        "EXEC-001",
        "correction",
        "Ana",
        "Fix",
        {"when": datetime(2026, 1, 1, tzinfo=UTC), "tags": ["a", "b"]},
    )

    read = store.events("EXEC-001")

    assert read[1] == written
    assert store.verify("EXEC-001") == []


def test_the_history_file_is_readable_markdown(
    store: HistoryStore, record: Path
) -> None:
    store.seal("EXEC-001")
    store.append("EXEC-001", "correction", "Ana", "Wrong environment.")

    text = history_path(record).read_text(encoding="utf-8")

    assert text.startswith("---\nrecord: EXEC-001\nevents:\n")
    assert "# History of EXEC-001" in text
    assert "2. " in text and "correction by Ana: Wrong environment." in text


@pytest.mark.parametrize(
    ("kind", "author", "justification", "match"),
    [
        ("edit", "Ana", "why", "kind must be one of"),
        ("correction", "  ", "why", "needs an author"),
        ("correction", "Ana", "", "needs a justification"),
    ],
)
def test_events_need_a_valid_kind_author_and_justification(
    store: HistoryStore, kind: str, author: str, justification: str, match: str
) -> None:
    store.seal("EXEC-001")

    with pytest.raises(ValueError, match=match):
        store.append("EXEC-001", kind, author, justification)

    assert len(store.events("EXEC-001")) == 1


def test_an_unsealed_record_takes_no_events(store: HistoryStore) -> None:
    with pytest.raises(HistoryError, match="not sealed yet"):
        store.append("EXEC-001", "correction", "Ana", "why")


def test_unserializable_details_are_rejected_without_writing(
    store: HistoryStore,
) -> None:
    store.seal("EXEC-001")

    with pytest.raises(HistoryError, match="cannot be part of a history event"):
        store.append("EXEC-001", "correction", "Ana", "why", {"x": object()})

    assert len(store.events("EXEC-001")) == 1


def test_a_record_with_no_history_does_not_verify(store: HistoryStore) -> None:
    assert store.verify("EXEC-001") == ["it has no history, so it was never sealed."]


def test_editing_the_sealed_record_is_detected(
    store: HistoryStore, record: Path
) -> None:
    store.seal("EXEC-001")
    record.write_text(record.read_text("utf-8").replace("Body", "Changed"), "utf-8")

    problems = store.verify("EXEC-001")

    assert any("modified after it was finalized" in p for p in problems)


def test_deleting_the_sealed_record_is_detected(
    store: HistoryStore, record: Path
) -> None:
    store.seal("EXEC-001")
    record.unlink()

    assert any("record file is missing" in p for p in store.verify("EXEC-001"))


def test_editing_an_event_is_detected(store: HistoryStore, record: Path) -> None:
    store.seal("EXEC-001")
    store.append("EXEC-001", "correction", "Ana", "Original reason")
    path = history_path(record)
    path.write_text(
        path.read_text("utf-8").replace("Original reason", "Different reason", 1),
        "utf-8",
    )

    problems = store.verify("EXEC-001")

    assert any("event 2 was modified" in p for p in problems)


def test_removing_an_event_is_detected(store: HistoryStore, record: Path) -> None:
    store.seal("EXEC-001")
    store.append("EXEC-001", "correction", "Ana", "one")
    store.append("EXEC-001", "correction", "Ana", "two")
    path = history_path(record)
    lines = path.read_text("utf-8").split("\n")
    start = next(i for i, ln in enumerate(lines) if "sequence: 2" in ln)
    end = next(i for i, ln in enumerate(lines) if "sequence: 3" in ln)
    del lines[start:end]
    path.write_text("\n".join(lines), "utf-8")

    problems = store.verify("EXEC-001")

    assert any("removed or reordered" in p for p in problems)
    assert any("does not follow the previous event" in p for p in problems)


def test_a_corrupt_history_file_is_reported_not_hidden(
    store: HistoryStore, record: Path
) -> None:
    store.seal("EXEC-001")
    history_path(record).write_text("not a history", encoding="utf-8")

    with pytest.raises(HistoryError):
        store.events("EXEC-001")
    assert store.verify("EXEC-001")


def test_a_malformed_event_is_reported(store: HistoryStore, record: Path) -> None:
    history_path(record).write_text(
        "---\nrecord: EXEC-001\nevents:\n  - sequence: 1\n---\n", encoding="utf-8"
    )

    with pytest.raises(HistoryError, match="malformed"):
        store.events("EXEC-001")


def test_write_failures_are_reported_with_the_path(
    store: HistoryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path, text: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("qa_workbench.storage.history.write_text_atomic", broken)

    with pytest.raises(StorageError, match="Cannot write .*disk full"):
        store.seal("EXEC-001")
