"""Tests for DataTable responsiveness at small terminal sizes."""

import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.theme import SHELL_CSS


class TableHost(App[None]):
    CSS = SHELL_CSS

    def __init__(self, table: DataTable) -> None:
        super().__init__()
        self._table = table

    def compose(self) -> ComposeResult:
        yield Static("host")
        yield self._table


def _run_table(table: DataTable, size: tuple[int, int]) -> TableHost:
    host = TableHost(table)

    async def runner() -> None:
        async with host.run_test(size=size) as pilot:
            await pilot.pause()

    asyncio.run(runner())
    return host


def _wide_table() -> DataTable:
    """A table with many columns and long content."""
    columns = [
        "ID",
        "Title",
        "Description",
        "Status",
        "Priority",
        "Assignee",
        "Created",
        "Updated",
    ]
    rows = [
        (
            f"TC-{i:03d}",
            (
                f"TC-{i:03d}",
                f"Test Case {i}",
                f"Description for test case {i} with some length",
                "Active",
                "High",
                "User A",
                "2026-01-01",
                "2026-01-15",
            ),
        )
        for i in range(1, 21)
    ]
    return DataTable(columns, rows)


def _narrow_table() -> DataTable:
    """A table with few columns."""
    columns = ["ID", "Title", "Status"]
    rows = [
        (f"TC-{i:03d}", (f"TC-{i:03d}", f"Test Case {i}", "Active"))
        for i in range(1, 11)
    ]
    return DataTable(columns, rows)


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_table_renders_on_small_terminal(size: tuple[int, int]) -> None:
    """Table should render without crashing on small terminals."""
    _run_table(_narrow_table(), size)
    # Just verify it doesn't crash


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_wide_table_renders_on_small_terminal(size: tuple[int, int]) -> None:
    """Wide table should render without crashing on small terminals."""
    _run_table(_wide_table(), size)
    # Just verify it doesn't crash


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_table_navigation_works_on_small_terminal(size: tuple[int, int]) -> None:
    """Table keyboard navigation should work on small terminals."""

    async def runner(size: tuple[int, int]) -> None:
        table = _narrow_table()
        host = TableHost(table)
        async with host.run_test(size=size) as pilot:
            await pilot.pause()
            # The table should be focused
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("up")
            await pilot.pause()
            # Should not crash

    asyncio.run(runner(size))


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_empty_table_shows_empty_state(size: tuple[int, int]) -> None:
    """Empty table should show empty state on small terminals."""
    table = DataTable(
        ["ID", "Name"], empty_message="No data", empty_hint="Add some data"
    )
    host = TableHost(table)

    async def runner() -> None:
        async with host.run_test(size=size) as pilot:
            await pilot.pause()
            # EmptyState should be visible
            from qa_workbench.tui.components.states import EmptyState

            empty_state = host._table.query_one(EmptyState)
            assert empty_state.display

    asyncio.run(runner())
