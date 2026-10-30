"""Repository of Markdown records with YAML frontmatter.

Layout, per schema::

    <root>/<schema.directory>/<ID>.md
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_workbench.storage.atomic import write_text_atomic
from qa_workbench.storage.errors import (
    FrontmatterError,
    ImmutableFieldError,
    RecordFinalizedError,
    RecordNotFoundError,
    RecordValidationError,
    StorageError,
)
from qa_workbench.storage.frontmatter import dump_document, read_document
from qa_workbench.storage.history import HistoryEvent, HistoryStore
from qa_workbench.storage.ids import is_valid_id, next_id, parse_id
from qa_workbench.storage.validation import (
    RecordSchema,
    validate_links,
    validate_metadata,
)

MANAGED_FIELDS = ("id", "created_at", "updated_at")


@dataclass(frozen=True)
class Record:
    """A record read from disk."""

    id: str
    metadata: dict[str, Any]
    body: str
    path: Path


@dataclass(frozen=True)
class RecordListing:
    """Result of listing records.

    Files that cannot be read or fail validation are reported in ``errors``
    instead of being dropped, so a damaged record is never mistaken for a
    missing one.
    """

    records: tuple[Record, ...]
    errors: tuple[StorageError, ...]


def _now() -> datetime:
    return datetime.now().astimezone()


class MarkdownRepository:
    """Create, read, update, and list records for the registered schemas."""

    def __init__(self, root: Path, schemas: Iterable[RecordSchema]) -> None:
        self.root = root
        self._schemas: dict[str, RecordSchema] = {}
        for schema in schemas:
            if schema.prefix in self._schemas:
                raise ValueError(f"Duplicate schema for prefix {schema.prefix}.")
            self._schemas[schema.prefix] = schema
        self._history = HistoryStore(self.path_of)

    def create(
        self,
        prefix: str,
        fields: Mapping[str, Any],
        body: str | Callable[[dict[str, Any]], str] = "",
    ) -> Record:
        """Create a record with the next free id.

        ``id``, ``created_at``, and ``updated_at`` are managed here and cannot
        be passed in ``fields``. ``body`` is the Markdown text, or a function
        that builds it from the final metadata (which includes the new id).
        """
        schema = self._schema(prefix)
        managed = [name for name in MANAGED_FIELDS if name in fields]
        if managed:
            raise ValueError(
                f"{', '.join(managed)} are managed by the repository and cannot be "
                "set when creating a record."
            )
        folder = self.root / schema.directory
        existing = (
            [path.stem for path in folder.glob("*.md")] if folder.is_dir() else []
        )
        record_id = next_id(prefix, existing)
        stamp = _now()
        metadata = {
            "id": record_id,
            **fields,
            "created_at": stamp,
            "updated_at": stamp,
        }
        path = folder / f"{record_id}.md"
        text = body(metadata) if callable(body) else body
        self._check(schema, path, metadata, text)
        if path.exists():
            raise StorageError(f"Refusing to overwrite existing record {path}.")
        self._write(path, metadata, text)
        self._seal_if_final(schema, record_id, metadata)
        return Record(record_id, metadata, text, path)

    def get(self, record_id: str) -> Record:
        """Read and validate one record."""
        schema, path = self._locate(record_id)
        if not path.is_file():
            raise RecordNotFoundError(record_id)
        document = read_document(path)
        self._check(schema, path, document.metadata, document.body, record_id)
        return Record(record_id, document.metadata, document.body, path)

    def update(
        self,
        record_id: str,
        changes: Mapping[str, Any],
        body: str | None = None,
    ) -> Record:
        """Change fields and/or the body of a record.

        The id and ``created_at`` never change. ``updated_at`` is set by the
        repository on every update.
        """
        current = self.get(record_id)
        schema, path = self._locate(record_id)
        if current.metadata["status"] in schema.immutable_statuses:
            raise RecordFinalizedError(record_id, current.metadata["status"])
        if "id" in changes and changes["id"] != current.id:
            raise ImmutableFieldError(record_id, "id")
        if (
            "created_at" in changes
            and changes["created_at"] != (current.metadata["created_at"])
        ):
            raise ImmutableFieldError(record_id, "created_at")
        if "updated_at" in changes:
            raise ValueError("updated_at is managed by the repository.")

        metadata = {
            **current.metadata,
            **{k: v for k, v in changes.items() if k not in MANAGED_FIELDS},
            "updated_at": _now(),
        }
        new_body = current.body if body is None else body
        self._check(schema, path, metadata, new_body, record_id)
        self._write(path, metadata, new_body)
        self._seal_if_final(schema, record_id, metadata)
        return Record(record_id, metadata, new_body, path)

    def add_history_event(
        self,
        record_id: str,
        kind: str,
        author: str,
        justification: str,
        details: Mapping[str, Any] | None = None,
    ) -> HistoryEvent:
        """Record a correction or addition to a finalized record.

        The record itself is never changed; the event is appended to its
        history with an author, a timestamp, and a justification.
        """
        record = self.get(record_id)
        schema, _ = self._locate(record_id)
        if record.metadata["status"] not in schema.immutable_statuses:
            raise ValueError(
                f"{record_id} is not finalized; edit it directly instead of "
                "adding a history event."
            )
        return self._history.append(record_id, kind, author, justification, details)

    def history(self, record_id: str) -> list[HistoryEvent]:
        """The history events of a record, oldest first."""
        self._locate(record_id)
        return self._history.events(record_id)

    def verify(self, record_id: str) -> list[str]:
        """Integrity problems of a finalized record; empty when intact.

        Records that are not final have nothing to verify.
        """
        record = self.get(record_id)
        schema, _ = self._locate(record_id)
        if record.metadata["status"] not in schema.immutable_statuses:
            return []
        return self._history.verify(record_id)

    def verify_all(self, prefix: str) -> dict[str, list[str]]:
        """Integrity problems of every finalized record of a kind, by id."""
        problems: dict[str, list[str]] = {}
        for record_id in self.record_ids(prefix):
            try:
                found = self.verify(record_id)
            except StorageError as error:
                found = [str(error)]
            if found:
                problems[record_id] = found
        return problems

    @property
    def prefixes(self) -> tuple[str, ...]:
        """The record kinds this repository knows, in sorted order."""
        return tuple(sorted(self._schemas))

    def record_ids(self, prefix: str) -> list[str]:
        """Ids of the record files present for ``prefix``, without reading them.

        Files whose names are not ids of this kind are ignored.
        """
        folder = self.root / self._schema(prefix).directory
        if not folder.is_dir():
            return []
        return sorted(
            path.stem
            for path in folder.glob("*.md")
            if is_valid_id(path.stem) and parse_id(path.stem).prefix == prefix
        )

    def path_of(self, record_id: str) -> Path:
        """Where the record file lives (it may not exist)."""
        return self._locate(record_id)[1]

    def list_records(self, prefix: str, *, status: str | None = None) -> RecordListing:
        """List records of one kind ordered by id, optionally by status."""
        schema = self._schema(prefix)
        folder = self.root / schema.directory
        records: list[Record] = []
        errors: list[StorageError] = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.md")):
                if not is_valid_id(path.stem) or parse_id(path.stem).prefix != prefix:
                    continue
                try:
                    record = self.get(path.stem)
                except StorageError as error:
                    errors.append(error)
                    continue
                if status is None or record.metadata["status"] == status:
                    records.append(record)
        return RecordListing(tuple(records), tuple(errors))

    def _schema(self, prefix: str) -> RecordSchema:
        try:
            return self._schemas[prefix]
        except KeyError:
            known = ", ".join(sorted(self._schemas)) or "none"
            raise ValueError(
                f"No schema is registered for prefix {prefix!r}. Registered: {known}."
            ) from None

    def _locate(self, record_id: str) -> tuple[RecordSchema, Path]:
        try:
            parsed = parse_id(record_id)
        except ValueError:
            raise RecordNotFoundError(record_id) from None
        schema = self._schemas.get(parsed.prefix)
        if schema is None:
            raise RecordNotFoundError(record_id)
        return schema, self.root / schema.directory / f"{record_id}.md"

    def _check(
        self,
        schema: RecordSchema,
        path: Path,
        metadata: Mapping[str, Any],
        body: str,
        expected_id: str | None = None,
    ) -> None:
        problems = validate_metadata(
            schema, metadata, expected_id=expected_id or path.stem
        )
        problems += validate_links(body, document=path, root=self.root)
        if problems:
            raise RecordValidationError(path, tuple(problems))

    def _seal_if_final(
        self, schema: RecordSchema, record_id: str, metadata: Mapping[str, Any]
    ) -> None:
        if metadata["status"] in schema.immutable_statuses:
            self._history.seal(record_id)

    def _write(self, path: Path, metadata: dict[str, Any], body: str) -> None:
        try:
            text = dump_document(metadata, body)
        except FrontmatterError as error:
            raise FrontmatterError(path, error.reason) from error
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, text)
        except OSError as error:
            raise StorageError(f"Cannot write {path}: {error}") from error
