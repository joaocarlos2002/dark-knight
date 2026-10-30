"""Errors raised by Markdown storage."""

from pathlib import Path


class StorageError(Exception):
    """Base class for storage failures."""


class FrontmatterError(StorageError):
    """Raised when a file is not a valid Markdown document with frontmatter."""

    def __init__(self, path: Path | str, reason: str) -> None:
        super().__init__(f"Invalid Markdown record {path}: {reason}")
        self.path = path
        self.reason = reason


class RecordValidationError(StorageError):
    """Raised when a record breaks the rules of its schema.

    Every problem found is reported, not just the first one.
    """

    def __init__(self, path: Path | str, problems: tuple[str, ...]) -> None:
        listed = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"Record {path} is not valid:\n{listed}")
        self.path = path
        self.problems = problems


class RecordNotFoundError(StorageError):
    """Raised when no record exists for an id."""

    def __init__(self, record_id: str) -> None:
        super().__init__(f"Record {record_id} was not found.")
        self.record_id = record_id


class ImmutableFieldError(StorageError):
    """Raised when an update tries to change an immutable field."""

    def __init__(self, record_id: str, field: str) -> None:
        super().__init__(f"{field} of {record_id} is immutable and cannot change.")
        self.record_id = record_id
        self.field = field
