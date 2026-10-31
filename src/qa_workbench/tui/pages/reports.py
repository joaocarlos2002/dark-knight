"""Reports & Evidence page: browse saved reports and evidence records."""

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static

from qa_workbench.reports.writer import write_execution_report
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.tui.browse import ALL, BrowseData, filter_rows
from qa_workbench.tui.browse_reports import (
    EVIDENCE_COLUMNS,
    REPORT_COLUMNS,
    evidence_rows,
    report_detail,
    report_rows,
)
from qa_workbench.tui.components.evidence_viewer import (
    EvidenceViewer,
    prepare_evidence_data,
)
from qa_workbench.tui.components.states import EmptyState
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."


@register("reports")
class ReportsPage(Page):
    """Browse saved reports and evidence records."""

    BINDINGS = [
        Binding("f", "cycle_report_filter", "Filter reports"),
        Binding("e", "cycle_evidence_filter", "Filter evidence"),
        Binding("g", "generate_report", "Generate report"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._report_data = BrowseData(())
        self._evidence_data = BrowseData(())
        self._report_status = ALL
        self._evidence_status = ALL
        self._selected_report: str | None = None
        self._selected_evidence: str | None = None

    def compose(self) -> ComposeResult:
        # Reports section
        yield Static("SAVED REPORTS", classes="section-title")
        yield Input(
            placeholder="Search reports (Ctrl+K): words match id, title, type, source",
            classes="searchable",
            id="reports-search",
        )
        yield DataTable(
            REPORT_COLUMNS,
            empty_message="No saved reports.",
            empty_hint=(
                "Generate with 'Generate report' (G) or `batman reports execution`."
            ),
            id="reports-table",
        )
        yield Static("", id="reports-summary", markup=False)

        # Evidence section
        yield Static("EVIDENCE RECORDS", classes="section-title")
        yield Input(
            placeholder="Search evidence: words must match id, description, source",
            classes="searchable",
            id="evidence-search",
        )
        yield DataTable(
            EVIDENCE_COLUMNS,
            empty_message="No evidence records.",
            empty_hint="Add evidence with `batman evidence add`.",
            id="evidence-table",
        )
        yield Static("", id="evidence-summary", markup=False)

        # Detail area
        with Horizontal(id="reports-detail-area"):
            with Vertical(id="report-detail-box"):
                yield Static("", id="report-detail", markup=False)
            with Vertical(id="evidence-viewer-box"):
                # Mount a single EvidenceViewer that will be updated
                yield EvidenceViewer(None, id="evidence-viewer")

        yield Static("", id="reports-problems", markup=False)
        yield EmptyState(
            NO_PROJECT,
            "Open a project to browse reports and evidence.",
            id="reports-empty",
        )

    def focus_primary(self) -> None:
        table = self.query_one("#reports-table", DataTable)
        if table.display:
            table.focus()
        else:
            self.focus()

    def refresh_data(self) -> None:
        project = self.context.project
        if project is None:
            self._report_data = BrowseData(())
            self._evidence_data = BrowseData(())
            self._apply_reports(NO_PROJECT)
            self._apply_evidence(NO_PROJECT)
            return

        try:
            self._report_data = report_rows(self.context.repository())
            self._evidence_data = evidence_rows(self.context.repository())
        except (StorageError, OSError, ValueError) as error:
            self._report_data = BrowseData(())
            self._evidence_data = BrowseData(())
            self._apply_reports(
                f"{format_status(Status.FAILED)}  Reports/evidence could "
                f"not be read: {error}"
            )
            self._apply_evidence("")
            return

        self._apply_reports()
        self._apply_evidence()

    def _apply_reports(self, message: str = "") -> None:
        rows = filter_rows(
            self._report_data.rows, self._query_reports(), self._report_status
        )
        self.query_one("#reports-table", DataTable).set_rows(
            [(row.key, row.cells) for row in rows]
        )
        total = len(self._report_data.rows)
        shown = f"{len(rows)} of {total}" if len(rows) != total else str(total)
        summary = message or (
            f"{shown} report(s)   status filter: {self._report_status} (F)"
        )
        self.query_one("#reports-summary", Static).update(summary)
        self._select_report(rows[0].key if rows else None)

    def _apply_evidence(self, message: str = "") -> None:
        rows = filter_rows(
            self._evidence_data.rows, self._query_evidence(), self._evidence_status
        )
        self.query_one("#evidence-table", DataTable).set_rows(
            [(row.key, row.cells) for row in rows]
        )
        total = len(self._evidence_data.rows)
        shown = f"{len(rows)} of {total}" if len(rows) != total else str(total)
        summary = message or (
            f"{shown} evidence record(s)   status filter: {self._evidence_status} (E)"
        )
        self.query_one("#evidence-summary", Static).update(summary)
        problems = self.query_one("#reports-problems", Static)
        prob_text = []
        if self._report_data.problems:
            prob_text += [f"Reports: {p}" for p in self._report_data.problems[:3]]
        if self._evidence_data.problems:
            prob_text += [f"Evidence: {p}" for p in self._evidence_data.problems[:3]]
        problems.update("\n".join(prob_text) if prob_text else "")
        self._select_evidence(rows[0].key if rows else None)

    def _query_reports(self) -> str:
        return self.query_one("#reports-search", Input).value

    def _query_evidence(self) -> str:
        return self.query_one("#evidence-search", Input).value

    def _select_report(self, key: str | None) -> None:
        self._selected_report = key
        detail = self.query_one("#report-detail", Static)
        if key is None:
            detail.update("")
            return
        try:
            detail.update(report_detail(self.context.repository(), key))
        except (StorageError, OSError, ValueError) as error:
            detail.update(
                f"{format_status(Status.FAILED)}  {key} could not be read: {error}"
            )

    def _select_evidence(self, key: str | None) -> None:
        self._selected_evidence = key
        viewer = self.query_one("#evidence-viewer", EvidenceViewer)

        if key is None:
            viewer.set_data(None)
            return

        try:
            store = EvidenceStore(self.context.repository())
            data = prepare_evidence_data(store, key)
            if data is None:
                viewer.set_data(None)
                return
            viewer.set_data(data)
        except (StorageError, OSError, ValueError):
            viewer.set_data(None)

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        table_id = getattr(event, "table_id", "")
        if table_id == "reports-table" and event.key != self._selected_report:
            self._select_report(event.key)
        elif table_id == "evidence-table" and event.key != self._selected_evidence:
            self._select_evidence(event.key)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        if event.input.id == "reports-search":
            self._apply_reports()
        elif event.input.id == "evidence-search":
            self._apply_evidence()

    def action_cycle_report_filter(self) -> None:
        choices = [ALL, *sorted({row.status for row in self._report_data.rows})]
        index = (
            choices.index(self._report_status) if self._report_status in choices else 0
        )
        self._report_status = choices[(index + 1) % len(choices)]
        self._apply_reports()

    def action_cycle_evidence_filter(self) -> None:
        choices = [ALL, *sorted({row.status for row in self._evidence_data.rows})]
        index = (
            choices.index(self._evidence_status)
            if self._evidence_status in choices
            else 0
        )
        self._evidence_status = choices[(index + 1) % len(choices)]
        self._apply_evidence()

    def action_generate_report(self) -> None:
        """Generate an execution report for the selected execution."""
        if self._selected_report is None:
            self.app.notify("No report selected.", severity="warning")
            return
        # The selected report key is the execution ID for execution reports
        repo = self.context.repository()
        meta = _parse_report_metadata(
            repo.root / "reports" / f"{self._selected_report}.md"
        )
        if meta and meta.get("report") == "execution":
            source = meta.get("source")
            if source:
                try:
                    write_execution_report(repo, source)
                    self.app.notify(f"Regenerated report for {source}", timeout=3)
                    self.refresh_data()
                except Exception as error:
                    self.app.notify(
                        f"Failed to generate report: {error}", severity="error"
                    )


def _parse_report_metadata(path: Path) -> dict[str, Any] | None:
    """Read a report file and return its frontmatter metadata."""
    try:
        from qa_workbench.storage.frontmatter import read_document

        doc = read_document(path)
        return doc.metadata
    except Exception:
        return None
