"""Repository of Markdown records with YAML frontmatter.

Layout, per schema::

    <root>/<schema.directory>/<ID>.md
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from qa_workbench.storage.atomic import write_text_atomic
from qa_workbench.storage.errors import (
    FrontmatterError,
    ImmutableFieldError,
    RecordNotFoundError,
    RecordValidationError,
    StorageError,
)
from qa_workbench.storage.frontmatter import dump_document, read_document
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

    def create(self, prefix: str, fields: Mapping[str, Any], body: str = "") -> Record:
        """Create a record with the next free id.

        ``id``, ``created_at``, and ``updated_at`` are managed here and cannot
        be passed in ``fields``.
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
        self._check(schema, path, metadata, body)
        if path.exists():
            raise StorageError(f"Refusing to overwrite existing record {path}.")
        self._write(path, metadata, body)
        return Record(record_id, metadata, body, path)

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
        if "id" in changes and changes["id"] != current.id:
            raise ImmutableFieldError(record_id, "id")
        if (
            "created_at" in changes
            and changes["created_at"] != (current.metadata["created_at"])
        ):
            raise ImmutableFieldError(record_id, "created_at")
        if "updated_at" in changes:
            raise ValueError("updated_at is managed by the repository.")

        schema, path = self._locate(record_id)
        metadata = {
            **current.metadata,
            **{k: v for k, v in changes.items() if k not in MANAGED_FIELDS},
            "updated_at": _now(),
        }
        new_body = current.body if body is None else body
        self._check(schema, path, metadata, new_body, record_id)
        self._write(path, metadata, new_body)
        return Record(record_id, metadata, new_body, path)

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
