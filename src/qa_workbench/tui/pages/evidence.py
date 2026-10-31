"""Evidence: register files and check their integrity (spec 4.15)."""

from textual.binding import Binding

from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_reports import (
    EVIDENCE_COLUMNS,
    evidence_detail,
    evidence_rows,
)
from qa_workbench.tui.components.file_dialog import FileDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register


@register("evidence")
class EvidencePage(BrowserPage):
    noun = "evidence file"
    columns = EVIDENCE_COLUMNS
    empty_message = "No evidence yet."
    empty_hint = "Press A to add a file. Its SHA-256 is recorded."
    shortcuts_hint = "A add   V verify all"

    BINDINGS = [
        Binding("a", "add", "Add"),
        Binding("v", "verify", "Verify"),
    ]

    def load(self) -> BrowseData:
        return evidence_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return evidence_detail(self.context.repository(), key)

    def action_add(self) -> None:
        if self.writable_project() is None:
            return

        def chosen(path) -> None:
            if path is not None:
                self._describe(path)

        self.app.push_screen(FileDialog("Add evidence"), chosen)

    def _describe(self, path) -> None:
        fields = (
            FormField("description", "What it shows", required=True),
            FormField("source", "Where it came from", required=True, default="manual"),
        )
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                record = EvidenceStore(self.context.repository()).register(
                    path, source=values["source"], description=values["description"]
                )
            except (StorageError, ValueError, OSError) as error:
                return str(error)
            sha = record.metadata["sha256"][:12]
            outcome.append(f"{record.id} registered, sha256 {sha}...")
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None or not outcome:
                return
            self.refresh_data()
            self.app.notify(outcome[0], title="Evidence", timeout=8)

        self.app.push_screen(
            FormDialog(f"Add {path.name}", fields, submit_label="Add", commit=commit),
            done,
        )

    def action_verify(self) -> None:
        if self.context.project is None:
            self.app.notify("No project is open.", severity="warning")
            return
        try:
            problems = EvidenceStore(self.context.repository()).verify_all()
        except StorageError as error:
            self.app.notify(str(error), severity="error", title="Verify")
            return
        bad = {key: found for key, found in problems.items() if found}
        self.refresh_data()
        if not bad:
            self.app.notify("All evidence is intact.", title="Verify")
            return
        lines = [f"{key}: {found[0]}" for key, found in list(bad.items())[:4]]
        self.app.notify(
            f"{len(bad)} item(s) are not intact:\n" + "\n".join(lines),
            severity="error",
            title="Verify",
            timeout=12,
        )
