"""Log viewer with timestamps, levels, and search."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog, Static


class LogLevel(IntEnum):
    """Severity, ordered so levels can be compared."""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


@dataclass(frozen=True)
class LogEntry:
    """One log line."""

    timestamp: datetime
    level: LogLevel
    message: str


def format_entry(entry: LogEntry) -> str:
    """Render ``<timestamp> <LEVEL> <message>`` with an ISO 8601 timestamp."""
    stamp = entry.timestamp.isoformat(timespec="seconds")
    return f"{stamp} {entry.level.name:<7} {entry.message}"


def filter_entries(
    entries: Iterable[LogEntry],
    query: str = "",
    min_level: LogLevel | None = None,
) -> list[LogEntry]:
    """Keep entries at or above ``min_level`` whose text contains ``query``."""
    needle = query.strip().lower()
    return [
        entry
        for entry in entries
        if (min_level is None or entry.level >= min_level)
        and (not needle or needle in format_entry(entry).lower())
    ]


class LogViewer(Vertical):
    """Scrollable, searchable log list.

    The search field has the ``searchable`` class so the global "focus search"
    shortcut can find it.
    """

    def __init__(self, entries: Sequence[LogEntry] = (), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._entries: list[LogEntry] = list(entries)
        self._query = ""
        self._min_level: LogLevel | None = None

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search logs",
            id="log-search",
            classes="searchable",
        )
        yield Static(id="log-summary")
        yield RichLog(id="log-lines", wrap=True, markup=False, highlight=False)

    def on_mount(self) -> None:
        self._refresh()

    def set_entries(self, entries: Sequence[LogEntry]) -> None:
        self._entries = list(entries)
        self._refresh()

    def add_entry(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        self._refresh()

    def set_min_level(self, level: LogLevel | None) -> None:
        self._min_level = level
        self._refresh()

    def on_input_changed(self, event: Input.Changed) -> None:
        self._query = event.value
        self._refresh()

    def _refresh(self) -> None:
        visible = filter_entries(self._entries, self._query, self._min_level)
        log = self.query_one("#log-lines", RichLog)
        log.clear()
        for entry in visible:
            log.write(format_entry(entry))
        self.query_one("#log-summary", Static).update(
            f"{len(visible)} of {len(self._entries)} entries"
        )
