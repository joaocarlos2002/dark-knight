"""Knowledge Base: full-text search over everything the project has recorded."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Input, Static

from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.index import RecordIndex, SearchHit, SearchIndexError
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."
NOT_BUILT = (
    "The search index is not built yet. Press B to build it from the Markdown files."
)


def hit_cells(hit: SearchHit) -> tuple[str, ...]:
    return (hit.id, hit.prefix, hit.status, hit.title)


@register("knowledge-base")
class KnowledgeBasePage(Page):
    """Markdown stays the source of truth; the SQLite index is a disposable cache
    that can be rebuilt at any time (``B``)."""

    BINDINGS = [
        Binding("b", "rebuild_index", "Rebuild index"),
        Binding("f", "cycle_kind", "Kind"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._kind: str | None = None
        self._selected: str | None = None
        self._hits: dict[str, SearchHit] = {}

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="kb-summary", markup=False)
        yield Input(
            placeholder="Search everything recorded (press Enter)",
            classes="searchable",
            id="kb-search",
        )
        yield DataTable(
            ["ID", "Kind", "Status", "Title"],
            empty_message="Type a search and press Enter.",
            empty_hint="Every word is matched as a prefix, ignoring case and accents.",
            id="kb-results",
        )
        with VerticalScroll(id="kb-detail-box"):
            yield Static("", id="kb-detail", markup=False)

    def focus_primary(self) -> None:
        self.query_one("#kb-search", Input).focus()

    # -- state ------------------------------------------------------------------

    def _index(self) -> RecordIndex:
        return RecordIndex(self.context.repository())

    def refresh_data(self) -> None:
        if self.context.project is None:
            self._summary(NO_PROJECT)
            self._show([], "")
            return
        try:
            index = self._index()
            if not index.exists:
                self._summary(NOT_BUILT)
                self._show([], "")
                return
            report = index.sync()  # cheap: only records whose file changed
        except (StorageError, OSError) as error:
            self._failed(error)
            return
        self._summary(
            self._line(f"index up to date, {report.indexed} updated", report.errors)
        )
        self._search()

    def _line(self, state: str, errors: tuple = ()) -> str:
        kind = self._kind or "all kinds"
        damaged = (
            f"   {len(errors)} damaged record(s) are not indexed" if errors else ""
        )
        return f"{state}   kind: {kind} (F)   B rebuild index{damaged}"

    def _summary(self, text: str) -> None:
        self.query_one("#kb-summary", Static).update(text)

    def _failed(self, error: Exception) -> None:
        self._summary(f"{format_status(Status.FAILED)}  Search is unavailable: {error}")
        self._show([], "")

    # -- search ------------------------------------------------------------------

    def _search(self) -> None:
        query = self.query_one("#kb-search", Input).value.strip()
        if not query or self.context.project is None:
            self._show([], query)
            return
        try:
            hits = self._index().search(query, prefix=self._kind)
        except ValueError as error:
            self._show([], query)
            self._summary(str(error))
            return
        except SearchIndexError as error:
            self._failed(error)
            return
        self._show(hits, query)

    def _show(self, hits: list[SearchHit], query: str) -> None:
        self._hits = {hit.id: hit for hit in hits}
        table = self.query_one("#kb-results", DataTable)
        table.set_rows([(hit.id, hit_cells(hit)) for hit in hits])
        if query and not hits:
            self.query_one("#kb-detail", Static).update(f"Nothing matches '{query}'.")
        else:
            self._select(hits[0].id if hits else None)

    def _select(self, key: str | None) -> None:
        self._selected = key
        detail = self.query_one("#kb-detail", Static)
        if key is None:
            detail.update("")
            return
        hit = self._hits[key]
        try:
            record = self.context.repository().get(key)
        except StorageError as error:
            detail.update(f"{key} is in the index but cannot be read: {error}")
            return
        detail.update(
            f"{hit.id}  {hit.title}\n{hit.prefix}   {hit.status}   {hit.path}\n"
            f"Match: {hit.snippet}\n\n{record.body.strip()}"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._search()
        table = self.query_one("#kb-results").query_one(TextualDataTable)
        if table.display:
            table.focus()

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        if event.key is not None and event.key != self._selected:
            self._select(event.key)

    def action_cycle_kind(self) -> None:
        if self.context.project is None:
            return
        kinds = [None, *sorted(self.context.repository().prefixes)]
        current = kinds.index(self._kind) if self._kind in kinds else 0
        self._kind = kinds[(current + 1) % len(kinds)]
        self.refresh_data()

    def action_rebuild_index(self) -> None:
        project = self.context.project
        if project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return
        try:
            report = self._index().rebuild()
        except (StorageError, OSError) as error:
            self._failed(error)
            return
        message = f"Index rebuilt: {report.indexed} record(s) indexed."
        if report.errors:
            message += f" {len(report.errors)} damaged record(s) were not indexed."
        self.app.notify(message, severity="warning" if report.errors else "information")
        self.refresh_data()
