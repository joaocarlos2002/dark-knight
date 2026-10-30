"""Append-only, tamper-evident history for finalized records (NFR-004).

A finalized record is sealed: the SHA-256 of its file is stored as the first
history event. Later corrections and additions are appended as separate events
with an author, a timestamp, and a justification. Every event carries the hash
of the one before it, so changing or removing an event, or editing the sealed
record itself, is detected by :meth:`HistoryStore.verify`.

The history lives next to the record as ``<ID>.history.md``.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from qa_workbench.storage.atomic import write_text_atomic
from qa_workbench.storage.errors import FrontmatterError, HistoryError, StorageError
from qa_workbench.storage.frontmatter import dump_document, read_document

SEALED = "sealed"
CORRECTION = "correction"
ADDITION = "addition"
EVENT_KINDS = (CORRECTION, ADDITION)
SYSTEM_AUTHOR = "qa-workbench"
GENESIS = "0" * 64


@dataclass(frozen=True)
class HistoryEvent:
    """One entry of a record's history."""

    sequence: int
    kind: str
    timestamp: datetime
    author: str
    justification: str
    details: dict[str, Any]
    previous_hash: str
    hash: str


def history_path(record_path: Path) -> Path:
    """Where the history of the record at ``record_path`` is kept."""
    return record_path.with_name(f"{record_path.stem}.history.md")


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"{type(value).__name__} cannot be part of a history event")


def _digest(event: Mapping[str, Any]) -> str:
    body = {key: value for key, value in event.items() if key != "hash"}
    canonical = json.dumps(
        _jsonable(body), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now().astimezone()


def _as_mapping(event: HistoryEvent) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "kind": event.kind,
        "timestamp": event.timestamp,
        "author": event.author,
        "justification": event.justification,
        "details": event.details,
        "previous_hash": event.previous_hash,
        "hash": event.hash,
    }


class HistoryStore:
    """Reads, extends, and verifies the history of records.

    ``path_of`` maps a record id to the path of its Markdown file.
    """

    def __init__(self, path_of: Callable[[str], Path]) -> None:
        self._path_of = path_of

    def is_sealed(self, record_id: str) -> bool:
        return history_path(self._path_of(record_id)).is_file()

    def seal(self, record_id: str) -> HistoryEvent:
        """Record the hash of a record that has just been finalized."""
        record_path = self._path_of(record_id)
        if self.is_sealed(record_id):
            raise HistoryError(record_id, "it is already sealed.")
        if not record_path.is_file():
            raise HistoryError(record_id, "the record file does not exist.")
        return self._append(
            record_id,
            [],
            SEALED,
            SYSTEM_AUTHOR,
            "Record finalized.",
            {"record_sha256": sha256_file(record_path)},
        )

    def append(
        self,
        record_id: str,
        kind: str,
        author: str,
        justification: str,
        details: Mapping[str, Any] | None = None,
    ) -> HistoryEvent:
        """Add a correction or an addition to a sealed record."""
        if kind not in EVENT_KINDS:
            raise ValueError(f"kind must be one of {', '.join(EVENT_KINDS)}.")
        if not author.strip():
            raise ValueError("A history event needs an author.")
        if not justification.strip():
            raise ValueError("A history event needs a justification.")
        events = self.events(record_id)
        if not events:
            raise HistoryError(record_id, "it is not sealed yet.")
        return self._append(
            record_id,
            events,
            kind,
            author.strip(),
            justification.strip(),
            dict(details or {}),
        )

    def events(self, record_id: str) -> list[HistoryEvent]:
        """Every event, oldest first. Empty when the record was never sealed."""
        path = history_path(self._path_of(record_id))
        if not path.is_file():
            return []
        try:
            document = read_document(path)
        except FrontmatterError as error:
            raise HistoryError(record_id, error.reason) from error
        raw_events = document.metadata.get("events")
        if not isinstance(raw_events, list):
            raise HistoryError(record_id, "the 'events' field must be a list.")
        events: list[HistoryEvent] = []
        for raw in raw_events:
            try:
                events.append(
                    HistoryEvent(
                        sequence=raw["sequence"],
                        kind=raw["kind"],
                        timestamp=raw["timestamp"],
                        author=raw["author"],
                        justification=raw["justification"],
                        details=raw.get("details") or {},
                        previous_hash=raw["previous_hash"],
                        hash=raw["hash"],
                    )
                )
            except (KeyError, TypeError, AttributeError) as error:
                raise HistoryError(
                    record_id, f"an event is malformed ({error!r})."
                ) from error
        return events

    def verify(self, record_id: str) -> list[str]:
        """Return every integrity problem; an empty list means intact."""
        try:
            events = self.events(record_id)
        except HistoryError as error:
            return [error.reason]
        if not events:
            return ["it has no history, so it was never sealed."]
        problems: list[str] = []
        previous = GENESIS
        for position, event in enumerate(events, start=1):
            if event.sequence != position:
                problems.append(
                    f"event {position} has sequence {event.sequence}; an event was "
                    "removed or reordered."
                )
            if event.previous_hash != previous:
                problems.append(
                    f"event {position} does not follow the previous event; the "
                    "history was altered."
                )
            try:
                expected = _digest(_as_mapping(event))
            except TypeError as error:
                problems.append(f"event {position} is malformed ({error}).")
                expected = ""
            if expected and event.hash != expected:
                problems.append(f"event {position} was modified after it was written.")
            previous = event.hash

        first = events[0]
        sealed = first.details.get("record_sha256")
        if first.kind != SEALED or not isinstance(sealed, str):
            problems.append("the first event is not a seal with the record hash.")
        else:
            record_path = self._path_of(record_id)
            if not record_path.is_file():
                problems.append("the finalized record file is missing.")
            elif sha256_file(record_path) != sealed:
                problems.append(
                    "the record was modified after it was finalized; corrections "
                    "must be history events."
                )
        return problems

    def _append(
        self,
        record_id: str,
        events: list[HistoryEvent],
        kind: str,
        author: str,
        justification: str,
        details: dict[str, Any],
    ) -> HistoryEvent:
        fields: dict[str, Any] = {
            "sequence": len(events) + 1,
            "kind": kind,
            "timestamp": _now(),
            "author": author,
            "justification": justification,
            "details": details,
            "previous_hash": events[-1].hash if events else GENESIS,
        }
        try:
            digest = _digest(fields)
        except TypeError as error:
            raise HistoryError(record_id, f"{error}.") from error
        event = HistoryEvent(hash=digest, **fields)
        path = history_path(self._path_of(record_id))
        metadata = {
            "record": record_id,
            "events": [_as_mapping(item) for item in [*events, event]],
        }
        body = "\n".join(
            [f"# History of {record_id}", ""]
            + [
                f"{item.sequence}. {item.timestamp.isoformat()} — {item.kind} by "
                f"{item.author}: {item.justification}"
                for item in [*events, event]
            ]
        )
        try:
            write_text_atomic(path, dump_document(metadata, body))
        except OSError as error:
            raise StorageError(f"Cannot write {path}: {error}") from error
        return event
