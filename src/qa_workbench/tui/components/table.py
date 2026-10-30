"""Data table with an explicit empty state."""

from collections.abc import Sequence
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DataTable as TextualDataTable

from qa_workbench.tui.components.states import EmptyState

Row = tuple[str, Sequence[str]]


def validate_rows(columns: Sequence[str], rows: Sequence[Row]) -> None:
    """Reject rows that do not match the columns instead of truncating them."""
    seen: set[str] = set()
    for key, cells in rows:
        if key in seen:
            raise ValueError(f"Duplicate row key {key!r}.")
        seen.add(key)
        if len(cells) != len(columns):
            raise ValueError(
                f"Row {key!r} has {len(cells)} cells but the table has "
                f"{len(columns)} columns."
            )


class DataTable(Vertical):
    """A keyboard-navigable table of ``(key, cells)`` rows.

    Activating a row posts :class:`Activated` with the row key. With no rows it
    shows an :class:`EmptyState` instead of an empty grid.
    """

    class Activated(Message):
        """Posted when the user activates a row."""

        def __init__(self, key: str) -> None:
            super().__init__()
            self.key = key

    def __init__(
        self,
        columns: Sequence[str],
        rows: Sequence[Row] = (),
        empty_message: str = "No records.",
        empty_hint: str = "",
        **kwargs: Any,
    ) -> None:
        if not columns:
            raise ValueError("DataTable needs at least one column.")
        validate_rows(columns, rows)
        super().__init__(**kwargs)
        self._columns = tuple(columns)
        self._rows = list(rows)
        self._empty_message = empty_message
        self._empty_hint = empty_hint

    def compose(self) -> ComposeResult:
        table: TextualDataTable[str] = TextualDataTable(cursor_type="row")
        table.add_columns(*self._columns)
        yield table
        yield EmptyState(self._empty_message, self._empty_hint)

    def on_mount(self) -> None:
        self._refresh()

    def set_rows(self, rows: Sequence[Row]) -> None:
        validate_rows(self._columns, rows)
        self._rows = list(rows)
        self._refresh()

    def on_data_table_row_selected(self, event: TextualDataTable.RowSelected) -> None:
        event.stop()
        if event.row_key.value is not None:
            self.post_message(self.Activated(event.row_key.value))

    def _refresh(self) -> None:
        table = self.query_one(TextualDataTable)
        table.clear()
        for key, cells in self._rows:
            table.add_row(*cells, key=key)
        table.display = bool(self._rows)
        self.query_one(EmptyState).display = not self._rows
