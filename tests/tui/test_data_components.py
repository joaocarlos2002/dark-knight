import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from textual.app import App, ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Input, RichLog, Static

from qa_workbench.tui.components.logs import (
    LogEntry,
    LogLevel,
    LogViewer,
    filter_entries,
    format_entry,
)
from qa_workbench.tui.components.table import DataTable, validate_rows
from qa_workbench.tui.theme import SHELL_CSS

NOW = datetime(2026, 1, 1, 10, 0, 5, tzinfo=UTC)


def _entry(level: LogLevel, message: str) -> LogEntry:
    return LogEntry(NOW, level, message)


ENTRIES = [
    _entry(LogLevel.INFO, "Started execution EXEC-001"),
    _entry(LogLevel.WARNING, "Slow response from /login"),
    _entry(LogLevel.ERROR, "Assertion failed: expected 200"),
]


def test_entry_is_rendered_with_iso_timestamp_and_level() -> None:
    assert (
        format_entry(ENTRIES[0])
        == "2026-01-01T10:00:05+00:00 INFO    Started execution EXEC-001"
    )


def test_filter_without_criteria_keeps_everything() -> None:
    assert filter_entries(ENTRIES) == ENTRIES


def test_filter_by_text_is_case_insensitive() -> None:
    assert filter_entries(ENTRIES, "LOGIN") == [ENTRIES[1]]


def test_filter_by_minimum_level() -> None:
    assert filter_entries(ENTRIES, min_level=LogLevel.WARNING) == ENTRIES[1:]


def test_filter_combines_text_and_level() -> None:
    assert filter_entries(ENTRIES, "slow", LogLevel.ERROR) == []


def test_filter_can_match_the_level_name() -> None:
    assert filter_entries(ENTRIES, "error") == [ENTRIES[2]]


def test_rows_must_match_the_columns() -> None:
    with pytest.raises(ValueError, match="'TC-1' has 1 cells but the table has 2"):
        validate_rows(["ID", "Title"], [("TC-1", ["only one"])])


def test_row_keys_must_be_unique() -> None:
    with pytest.raises(ValueError, match="Duplicate row key 'TC-1'"):
        validate_rows(["ID"], [("TC-1", ["a"]), ("TC-1", ["b"])])


def test_table_needs_a_column() -> None:
    with pytest.raises(ValueError, match="at least one column"):
        DataTable([])


def _show(
    widget: Widget, check: Callable[[App[None], Widget, object], Awaitable[None]]
) -> None:
    class Host(App[None]):
        CSS = SHELL_CSS

        def __init__(self) -> None:
            super().__init__()
            self.selected: list[str] = []

        def compose(self) -> ComposeResult:
            yield widget

        def on_data_table_activated(self, event: DataTable.Activated) -> None:
            self.selected.append(event.key)

    async def runner() -> None:
        app = Host()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await check(app, widget, pilot)

    asyncio.run(runner())


def test_empty_table_shows_the_empty_state() -> None:
    async def check(app: App[None], widget: Widget, pilot: object) -> None:
        assert not widget.query_one(TextualDataTable).display
        empty = widget.query_one(Static)
        assert empty.display
        assert "No test cases." in str(empty.render())

    _show(DataTable(["ID"], empty_message="No test cases."), check)


def test_table_shows_rows_and_reports_the_selected_key() -> None:
    table = DataTable(
        ["ID", "Title"],
        [("TC-001", ["TC-001", "Login"]), ("TC-002", ["TC-002", "Signup"])],
    )

    async def check(app: App[None], widget: Widget, pilot) -> None:
        assert widget.query_one(TextualDataTable).row_count == 2
        await pilot.press("down", "enter")
        assert app.selected == ["TC-002"]  # type: ignore[attr-defined]

    _show(table, check)


def test_set_rows_replaces_the_content_and_validates() -> None:
    table = DataTable(["ID"], [("A", ["A"])])

    async def check(app: App[None], widget: Widget, pilot) -> None:
        assert isinstance(widget, DataTable)
        widget.set_rows([("B", ["B"]), ("C", ["C"])])
        assert widget.query_one(TextualDataTable).row_count == 2
        with pytest.raises(ValueError, match="cells"):
            widget.set_rows([("D", ["x", "y"])])
        assert widget.query_one(TextualDataTable).row_count == 2
        widget.set_rows([])
        assert widget.query_one(Static).display

    _show(table, check)


def _log_lines(widget: Widget) -> list[str]:
    return [strip.text for strip in widget.query_one(RichLog).lines]


def test_log_viewer_shows_entries_and_a_summary() -> None:
    async def check(app: App[None], widget: Widget, pilot) -> None:
        assert len(_log_lines(widget)) == 3
        assert str(widget.query_one("#log-summary", Static).render()) == (
            "3 of 3 entries"
        )

    _show(LogViewer(ENTRIES), check)


def test_log_viewer_search_filters_the_lines() -> None:
    async def check(app: App[None], widget: Widget, pilot) -> None:
        search = widget.query_one(Input)
        search.focus()
        await pilot.press(*"login")
        await pilot.pause()
        lines = _log_lines(widget)
        assert len(lines) == 1
        assert "Slow response" in lines[0]
        assert str(widget.query_one("#log-summary", Static).render()) == (
            "1 of 3 entries"
        )

    _show(LogViewer(ENTRIES), check)


def test_log_viewer_filters_by_level_and_accepts_new_entries() -> None:
    async def check(app: App[None], widget: Widget, pilot) -> None:
        assert isinstance(widget, LogViewer)
        widget.set_min_level(LogLevel.ERROR)
        assert len(_log_lines(widget)) == 1
        widget.add_entry(_entry(LogLevel.ERROR, "Timeout"))
        assert len(_log_lines(widget)) == 2
        widget.set_min_level(None)
        assert len(_log_lines(widget)) == 4

    _show(LogViewer(ENTRIES), check)


def test_search_field_is_discoverable_by_the_global_shortcut() -> None:
    async def check(app: App[None], widget: Widget, pilot) -> None:
        assert widget.query_one(Input).has_class("searchable")

    _show(LogViewer(), check)
