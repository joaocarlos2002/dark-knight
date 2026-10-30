from pathlib import Path

import pytest

from qa_workbench.storage.errors import (
    HistoryError,
    RecordFinalizedError,
    RecordNotFoundError,
)
from qa_workbench.storage.history import history_path
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema

EXECUTIONS = RecordSchema(
    prefix="EXEC",
    directory="executions",
    statuses=frozenset({"created", "running", "finalized"}),
    immutable_statuses=frozenset({"finalized"}),
)


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [EXECUTIONS])


def _finalized(repo: MarkdownRepository):
    running = repo.create("EXEC", {"status": "running"}, "Steps\n")
    return repo.update(running.id, {"status": "finalized"}, "Steps and result\n")


def test_schema_rejects_final_statuses_it_does_not_allow() -> None:
    with pytest.raises(ValueError, match="immutable_statuses must be allowed"):
        RecordSchema(
            "EXEC", "executions", frozenset({"a"}), immutable_statuses=frozenset({"b"})
        )


def test_records_can_be_edited_until_they_are_finalized(
    repo: MarkdownRepository,
) -> None:
    record = repo.create("EXEC", {"status": "created"})

    repo.update(record.id, {"status": "running"}, "In progress\n")
    repo.update(record.id, {"status": "running"}, "More progress\n")

    assert not history_path(record.path).exists()


def test_finalizing_seals_the_record(repo: MarkdownRepository) -> None:
    record = _finalized(repo)

    events = repo.history(record.id)

    assert [e.kind for e in events] == ["sealed"]
    assert history_path(record.path).is_file()
    assert repo.verify(record.id) == []


def test_creating_a_record_that_is_already_final_seals_it(
    repo: MarkdownRepository,
) -> None:
    record = repo.create("EXEC", {"status": "finalized"})

    assert [e.kind for e in repo.history(record.id)] == ["sealed"]
    assert repo.verify(record.id) == []


def test_a_finalized_record_cannot_be_edited(repo: MarkdownRepository) -> None:
    record = _finalized(repo)
    before = record.path.read_text(encoding="utf-8")

    with pytest.raises(RecordFinalizedError, match="EXEC-001 is finalized") as error:
        repo.update(record.id, {}, "Rewritten history\n")

    assert "separate history event" in str(error.value)
    assert record.path.read_text(encoding="utf-8") == before
    assert repo.verify(record.id) == []


def test_not_even_the_status_of_a_finalized_record_can_change(
    repo: MarkdownRepository,
) -> None:
    record = _finalized(repo)

    with pytest.raises(RecordFinalizedError):
        repo.update(record.id, {"status": "running"})


def test_corrections_are_separate_events_with_author_and_justification(
    repo: MarkdownRepository,
) -> None:
    record = _finalized(repo)

    event = repo.add_history_event(
        record.id,
        "correction",
        "Ana",
        "The environment was staging, not production.",
        {"environment": "staging"},
    )

    assert event.sequence == 2
    assert event.author == "Ana"
    assert event.timestamp.utcoffset() is not None
    assert [e.kind for e in repo.history(record.id)] == ["sealed", "correction"]
    assert repo.get(record.id).body == "Steps and result\n"
    assert repo.verify(record.id) == []


def test_events_need_an_author_and_a_justification(
    repo: MarkdownRepository,
) -> None:
    record = _finalized(repo)

    with pytest.raises(ValueError, match="needs a justification"):
        repo.add_history_event(record.id, "correction", "Ana", " ")
    with pytest.raises(ValueError, match="needs an author"):
        repo.add_history_event(record.id, "addition", "", "why")


def test_only_finalized_records_take_history_events(
    repo: MarkdownRepository,
) -> None:
    record = repo.create("EXEC", {"status": "running"})

    with pytest.raises(ValueError, match="is not finalized; edit it directly"):
        repo.add_history_event(record.id, "correction", "Ana", "why")


def test_editing_a_finalized_file_by_hand_is_detected(
    repo: MarkdownRepository,
) -> None:
    record = _finalized(repo)
    record.path.write_text(
        record.path.read_text(encoding="utf-8").replace("result", "RESULT"),
        encoding="utf-8",
    )

    problems = repo.verify(record.id)

    assert any("modified after it was finalized" in p for p in problems)
    assert list(repo.verify_all("EXEC")) == [record.id]


def test_tampering_with_the_history_is_detected(repo: MarkdownRepository) -> None:
    record = _finalized(repo)
    repo.add_history_event(record.id, "correction", "Ana", "Original reason")
    path = history_path(record.path)
    path.write_text(
        path.read_text(encoding="utf-8").replace("Original reason", "Other", 1),
        encoding="utf-8",
    )

    assert any("event 2 was modified" in p for p in repo.verify(record.id))


def test_a_finalized_record_whose_seal_was_deleted_is_reported(
    repo: MarkdownRepository,
) -> None:
    record = _finalized(repo)
    history_path(record.path).unlink()

    assert repo.verify(record.id) == ["it has no history, so it was never sealed."]


def test_verify_all_lists_only_records_with_problems(
    repo: MarkdownRepository,
) -> None:
    good = _finalized(repo)
    bad = _finalized(repo)
    bad.path.write_text(
        bad.path.read_text(encoding="utf-8") + "extra\n", encoding="utf-8"
    )
    repo.create("EXEC", {"status": "running"})

    assert list(repo.verify_all("EXEC")) == [bad.id]
    assert repo.verify(good.id) == []


def test_records_that_are_not_final_have_nothing_to_verify(
    repo: MarkdownRepository,
) -> None:
    record = repo.create("EXEC", {"status": "running"})

    assert repo.verify(record.id) == []


def test_history_files_are_not_mistaken_for_records(
    repo: MarkdownRepository,
) -> None:
    record = _finalized(repo)

    assert repo.record_ids("EXEC") == [record.id]
    assert [r.id for r in repo.list_records("EXEC").records] == [record.id]


def test_unknown_ids_have_no_history(repo: MarkdownRepository) -> None:
    with pytest.raises(RecordNotFoundError):
        repo.history("BUG-001")
    with pytest.raises(HistoryError):
        repo._history.append("EXEC-009", "correction", "Ana", "why")
