import os
import sqlite3
from pathlib import Path

import pytest

from qa_workbench.storage.errors import FrontmatterError
from qa_workbench.storage.index import (
    INDEX_VERSION,
    IndexNotBuiltError,
    RecordIndex,
    SearchIndexError,
    build_match_query,
)
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema

TEST_CASES = RecordSchema(
    prefix="TC",
    directory="test-cases",
    statuses=frozenset({"draft", "active", "retired"}),
    required=("title",),
)
REQUIREMENTS = RecordSchema(
    prefix="REQ", directory="requirements", statuses=frozenset({"open", "closed"})
)


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [TEST_CASES, REQUIREMENTS])


@pytest.fixture
def populated(repo: MarkdownRepository) -> MarkdownRepository:
    repo.create(
        "TC",
        {"title": "Autenticação com credenciais válidas", "status": "active"},
        "Validar o acesso de um usuário.",
    )
    repo.create(
        "TC",
        {"title": "Recuperar senha", "status": "draft", "tags": ["login", "email"]},
        "Enviar link por e-mail.",
    )
    repo.create("REQ", {"status": "open"}, "O sistema deve permitir login.")
    return repo


def test_build_match_query_turns_words_into_safe_prefix_terms() -> None:
    assert build_match_query("login válido") == '"login"* "válido"*'


def test_build_match_query_drops_punctuation_and_operators() -> None:
    assert build_match_query('x" OR "y -z* (a)') == '"x"* "OR"* "y"* "z"* "a"*'


@pytest.mark.parametrize("query", ["", "   ", "!!! ???", '""'])
def test_a_query_without_words_is_rejected(query: str) -> None:
    with pytest.raises(ValueError, match="at least one word"):
        build_match_query(query)


def test_rebuild_indexes_every_record_kind(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)

    report = index.rebuild()

    assert (report.indexed, report.unchanged, report.removed) == (3, 0, 0)
    assert report.errors == ()
    assert index.path == populated.root / "indexes" / "records.sqlite"
    assert index.exists


def test_search_finds_text_in_title_and_body(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    by_title = index.search("credenciais")
    by_body = index.search("usuário")

    assert [h.id for h in by_title] == ["TC-001"]
    assert [h.id for h in by_body] == ["TC-001"]


def test_search_ignores_case_and_accents(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    assert [h.id for h in index.search("AUTENTICACAO")] == ["TC-001"]
    assert [h.id for h in index.search("usuario")] == ["TC-001"]


def test_search_matches_word_prefixes(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    assert [h.id for h in index.search("recup")] == ["TC-002"]


def test_search_requires_every_word(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    assert [h.id for h in index.search("recuperar email")] == ["TC-002"]
    assert index.search("recuperar credenciais") == []


def test_search_finds_ids_and_tags(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    assert [h.id for h in index.search("TC-002")] == ["TC-002"]
    # "email" is only a tag; the body spells it "e-mail".
    assert [h.id for h in index.search("email")] == ["TC-002"]


def test_search_filters_by_kind_and_status(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    assert {h.id for h in index.search("login")} == {"TC-002", "REQ-001"}
    assert [h.id for h in index.search("login", prefix="REQ")] == ["REQ-001"]
    assert [h.id for h in index.search("login", status="draft")] == ["TC-002"]
    assert index.search("login", prefix="REQ", status="draft") == []


def test_hits_carry_title_status_path_and_a_snippet(
    populated: MarkdownRepository,
) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    hit = index.search("link")[0]

    assert hit.id == "TC-002"
    assert hit.prefix == "TC"
    assert hit.status == "draft"
    assert hit.title == "Recuperar senha"
    assert hit.path == "test-cases/TC-002.md"
    assert "[link]" in hit.snippet


def test_search_respects_the_limit(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    assert len(index.search("login", limit=1)) == 1
    with pytest.raises(ValueError, match="limit must be at least 1"):
        index.search("login", limit=0)


def test_search_before_building_fails_explicitly(
    populated: MarkdownRepository,
) -> None:
    with pytest.raises(IndexNotBuiltError, match="does not exist yet"):
        RecordIndex(populated).search("login")


def test_the_index_is_disposable_and_rebuilds_identically(
    populated: MarkdownRepository,
) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    before = index.search("login")

    index.path.unlink()
    index.rebuild()

    assert index.search("login") == before


def test_rebuild_replaces_a_damaged_index(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    index.path.write_bytes(b"this is not a sqlite database at all" * 100)

    with pytest.raises(SearchIndexError, match="damaged or not an index") as error:
        index.search("login")
    assert "rebuild it" in str(error.value)

    index.rebuild()
    assert index.search("login")


def test_a_wrong_version_asks_for_a_rebuild(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    db = sqlite3.connect(index.path)
    db.execute(f"PRAGMA user_version = {INDEX_VERSION + 1}")
    db.close()

    with pytest.raises(SearchIndexError, match="has version"):
        index.search("login")


def test_sync_skips_unchanged_records(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()

    report = index.sync()

    assert (report.indexed, report.unchanged, report.removed) == (0, 3, 0)


def test_sync_picks_up_changed_records(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    populated.update("TC-002", {"status": "active"}, "Nova descrição sobre cookies.")

    report = index.sync()

    assert (report.indexed, report.unchanged) == (1, 2)
    assert [h.id for h in index.search("cookies")] == ["TC-002"]
    assert index.search("link") == []
    assert [h.id for h in index.search("recuperar", status="active")] == ["TC-002"]


def test_sync_picks_up_new_records(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    populated.create("TC", {"title": "Logout", "status": "draft"}, "Encerrar sessão.")

    report = index.sync()

    assert report.indexed == 1
    assert [h.id for h in index.search("logout")] == ["TC-003"]


def test_sync_removes_deleted_records(populated: MarkdownRepository) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    populated.path_of("TC-001").unlink()

    report = index.sync()

    assert report.removed == 1
    assert index.search("credenciais") == []


def test_damaged_records_are_reported_and_not_indexed(
    populated: MarkdownRepository,
) -> None:
    populated.path_of("TC-002").write_text("not a record", encoding="utf-8")
    index = RecordIndex(populated)

    report = index.rebuild()

    assert report.indexed == 2
    assert len(report.errors) == 1
    assert isinstance(report.errors[0], FrontmatterError)
    assert "TC-002.md" in str(report.errors[0])
    assert index.search("recuperar") == []


def test_a_record_that_becomes_damaged_leaves_the_index_on_sync(
    populated: MarkdownRepository,
) -> None:
    index = RecordIndex(populated)
    index.rebuild()
    path = populated.path_of("TC-002")
    path.write_text("broken", encoding="utf-8")
    os.utime(path, ns=(1, 1))

    report = index.sync()

    assert len(report.errors) == 1
    assert index.search("recuperar") == []


def test_an_empty_repository_builds_an_empty_index(repo: MarkdownRepository) -> None:
    index = RecordIndex(repo)

    report = index.rebuild()

    assert (report.indexed, report.removed, report.errors) == (0, 0, ())
    assert index.search("anything") == []


def test_the_index_location_can_be_chosen(
    populated: MarkdownRepository, tmp_path: Path
) -> None:
    index = RecordIndex(populated, tmp_path / "elsewhere" / "idx.sqlite")

    index.rebuild()

    assert (tmp_path / "elsewhere" / "idx.sqlite").is_file()
    assert not (populated.root / "indexes").exists()
