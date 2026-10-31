"""A list + detail page: search, a status filter, and the selected record."""

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Input, Static

from qa_workbench.projects.models import Project
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import ALL, BrowseData, BrowseRow, filter_rows
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."


class BrowserPage(Page):
    """Subclasses say what to list (:meth:`load`) and how to describe one record
    (:meth:`describe`); search, filtering, and selection are handled here."""

    noun = "record"
    columns: Sequence[str] = ()
    empty_message = "No records."
    empty_hint = ""
    shortcuts_hint = ""

    BINDINGS = [Binding("f", "cycle_filter", "Filter")]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._data = BrowseData(())
        self._status = ALL
        self._selected: str | None = None

    # -- to override -----------------------------------------------------------

    def load(self) -> BrowseData:
        raise NotImplementedError

    def describe(self, key: str) -> str:
        raise NotImplementedError

    # -- layout ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="browse-summary", markup=False)
        yield Input(
            placeholder="Search (Ctrl+K): words must match id, title, status, tags",
            classes="searchable",
            id="browse-search",
        )
        yield DataTable(
            self.columns,
            empty_message=self.empty_message,
            empty_hint=self.empty_hint,
            id="browse-table",
        )
        with VerticalScroll(id="browse-detail-box"):
            yield Static("", id="browse-detail", markup=False)
        yield Static("", id="browse-problems", markup=False)

    def focus_primary(self) -> None:
        table = self.table()
        if table.display:
            table.focus()
        else:
            self.focus()

    # -- data ----------------------------------------------------------------------

    def refresh_data(self) -> None:
        project = self.context.project
        if project is None:
            self._data = BrowseData(())
            self._apply(NO_PROJECT)
            return
        try:
            self._data = self.load()
        except (StorageError, OSError, ValueError) as error:
            self._data = BrowseData(())
            self._apply(
                f"{format_status(Status.FAILED)}  The {self.noun}s could not be "
                f"read: {error}"
            )
            return
        self._apply()

    def _query(self) -> str:
        return self.query_one("#browse-search", Input).value

    def _statuses(self) -> list[str]:
        return [ALL, *sorted({row.status for row in self._data.rows})]

    def _apply(self, message: str = "") -> None:
        rows = filter_rows(self._data.rows, self._query(), self._status)
        self.query_one("#browse-table", DataTable).set_rows(
            [(row.key, row.cells) for row in rows]
        )
        total = len(self._data.rows)
        shown = f"{len(rows)} of {total}" if len(rows) != total else str(total)
        summary = message or (
            f"{shown} {self.noun}(s)   status filter: {self._status} (F)"
            + (f"   {self.shortcuts_hint}" if self.shortcuts_hint else "")
        )
        self.query_one("#browse-summary", Static).update(summary)
        problems = self.query_one("#browse-problems", Static)
        problems.update(
            f"{len(self._data.problems)} damaged record(s) are not listed:\n"
            + "\n".join(f"  - {p}" for p in self._data.problems[:5])
            if self._data.problems
            else ""
        )
        self._select(rows[0].key if rows else None)

    # -- selection ---------------------------------------------------------------------

    def _select(self, key: str | None) -> None:
        self._selected = key
        detail = self.query_one("#browse-detail", Static)
        if key is None:
            detail.update("")
            return
        try:
            detail.update(self.describe(key))
        except (StorageError, OSError, ValueError) as error:
            detail.update(
                f"{format_status(Status.FAILED)}  {key} could not be read: {error}"
            )

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        if event.key != self._selected:
            self._select(event.key)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self._apply()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.focus_primary()

    def action_cycle_filter(self) -> None:
        choices = self._statuses()
        index = choices.index(self._status) if self._status in choices else 0
        self._status = choices[(index + 1) % len(choices)]
        self._apply()

    # -- helpers for subclasses ---------------------------------------------

    def writable_project(self) -> Project | None:
        """The open project if it can be changed; otherwise say why and return None."""
        project = self.context.project
        if project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return None
        if project.archived:
            self.app.notify(
                f"{project.id} is archived and cannot be changed.", severity="warning"
            )
            return None
        return project

    def selected_key(self) -> str | None:
        return self._selected

    def table(self) -> TextualDataTable:
        return self.query_one("#browse-table").query_one(TextualDataTable)


__all__ = ["BrowseRow", "BrowserPage"]
