"""Rebuildable SQLite search index (REQ-008).

The Markdown files are the source of truth. The index is a disposable cache:
it can be deleted at any time and rebuilt from the records, and nothing is
ever read back from it except search results.
"""

import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository, Record

INDEX_VERSION = 1
DEFAULT_INDEX = Path("indexes") / "records.sqlite"

_WORDS = re.compile(r"\w+")

_SCHEMA = """
CREATE TABLE meta (
    record_id TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL
);
CREATE VIRTUAL TABLE fts USING fts5(
    record_id UNINDEXED,
    prefix UNINDEXED,
    status UNINDEXED,
    title,
    path UNINDEXED,
    ident,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


class SearchIndexError(StorageError):
    """Raised when the index cannot be used. Rebuilding it is the fix."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(
            f"Search index {path} {reason} It is only a cache: rebuild it from "
            "the Markdown records."
        )
        self.path = path
        self.reason = reason


class IndexNotBuiltError(SearchIndexError):
    """Raised when searching before the index was built."""

    def __init__(self, path: Path) -> None:
        super().__init__(path, "does not exist yet.")


@dataclass(frozen=True)
class SearchHit:
    """One search result."""

    id: str
    prefix: str
    status: str
    title: str
    path: str
    snippet: str


@dataclass(frozen=True)
class IndexReport:
    """What a rebuild or sync did.

    Records that are damaged or invalid are not indexed; they are reported in
    ``errors`` so they cannot be mistaken for missing records.
    """

    indexed: int
    unchanged: int
    removed: int
    errors: tuple[StorageError, ...]


def build_match_query(query: str) -> str:
    """Turn user text into a safe FTS5 expression: every word, as a prefix."""
    words = _WORDS.findall(query)
    if not words:
        raise ValueError("Search needs at least one word.")
    return " ".join(f'"{word}"*' for word in words)


def _text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return "" if value is None else str(value)


class RecordIndex:
    """A SQLite full-text index over the records of a repository."""

    def __init__(self, repository: MarkdownRepository, path: Path | None = None):
        self._repository = repository
        self.path = path or repository.root / DEFAULT_INDEX

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def rebuild(self) -> IndexReport:
        """Delete the index and build it again from every record."""
        for leftover in (self.path, Path(f"{self.path}-wal"), Path(f"{self.path}-shm")):
            leftover.unlink(missing_ok=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect(create=True) as db:
            return self._sync(db)

    def sync(self) -> IndexReport:
        """Bring an existing index up to date, touching only what changed."""
        with self._connect() as db:
            return self._sync(db)

    def search(
        self,
        query: str,
        *,
        prefix: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SearchHit]:
        """Full-text search ordered by relevance.

        Matching ignores case and accents and treats each word as a prefix.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}.")
        match = build_match_query(query)
        sql = (
            "SELECT record_id, prefix, status, title, path, "
            "snippet(fts, 6, '[', ']', '…', 12) "
            "FROM fts WHERE fts MATCH ?"
        )
        params: list[Any] = [match]
        if prefix is not None:
            sql += " AND prefix = ?"
            params.append(prefix)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY bm25(fts) LIMIT ?"
        params.append(limit)
        with self._connect() as db:
            try:
                rows = db.execute(sql, params).fetchall()
            except sqlite3.DatabaseError as error:
                raise SearchIndexError(self.path, f"failed: {error}.") from error
        return [SearchHit(*row) for row in rows]

    def _connect(self, create: bool = False) -> "_Connection":
        if not create and not self.path.is_file():
            raise IndexNotBuiltError(self.path)
        db = None
        try:
            db = sqlite3.connect(self.path)
            if create:
                db.executescript(_SCHEMA)
                db.execute(f"PRAGMA user_version = {INDEX_VERSION}")
            else:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                if version != INDEX_VERSION:
                    raise SearchIndexError(
                        self.path,
                        f"has version {version}, but version {INDEX_VERSION} "
                        "is expected.",
                    )
                db.execute("SELECT count(*) FROM meta").fetchone()
        except SearchIndexError:
            if db is not None:
                db.close()
            raise
        except sqlite3.DatabaseError as error:
            if db is not None:
                db.close()
            raise SearchIndexError(
                self.path, f"is damaged or not an index ({error})."
            ) from error
        return _Connection(db)

    def _sync(self, db: "_Connection") -> IndexReport:
        indexed = unchanged = 0
        errors: list[StorageError] = []
        seen: set[str] = set()
        known = {
            row[0]: (row[1], row[2])
            for row in db.execute("SELECT record_id, mtime_ns, size FROM meta")
        }
        for prefix in self._repository.prefixes:
            for record_id in self._repository.record_ids(prefix):
                seen.add(record_id)
                path = self._repository.path_of(record_id)
                stat = path.stat()
                if known.get(record_id) == (stat.st_mtime_ns, stat.st_size):
                    unchanged += 1
                    continue
                try:
                    record = self._repository.get(record_id)
                except StorageError as error:
                    errors.append(error)
                    self._remove(db, record_id)
                    seen.discard(record_id)
                    continue
                self._upsert(db, record, stat.st_mtime_ns, stat.st_size)
                indexed += 1
        removed = 0
        for record_id in set(known) - seen:
            self._remove(db, record_id)
            removed += 1
        db.commit()
        return IndexReport(indexed, unchanged, removed, tuple(errors))

    def _upsert(
        self, db: "_Connection", record: Record, mtime_ns: int, size: int
    ) -> None:
        self._remove(db, record.id)
        metadata = record.metadata
        relative = record.path.relative_to(self._repository.root).as_posix()
        searchable = " ".join(
            part for part in (_text(metadata.get("tags")), record.body) if part
        )
        db.execute(
            "INSERT INTO fts (record_id, prefix, status, title, path, ident, body) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.id.rsplit("-", 1)[0],
                _text(metadata.get("status")),
                _text(metadata.get("title")),
                relative,
                record.id,
                searchable,
            ),
        )
        db.execute(
            "INSERT INTO meta (record_id, mtime_ns, size) VALUES (?, ?, ?)",
            (record.id, mtime_ns, size),
        )

    @staticmethod
    def _remove(db: "_Connection", record_id: str) -> None:
        db.execute("DELETE FROM fts WHERE record_id = ?", (record_id,))
        db.execute("DELETE FROM meta WHERE record_id = ?", (record_id,))


class _Connection:
    """A SQLite connection that closes itself and commits only on success."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *exc: object) -> None:
        self._db.close()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self._db.execute(sql, tuple(params))

    def commit(self) -> None:
        self._db.commit()
