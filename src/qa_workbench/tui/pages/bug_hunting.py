"""Bug hunting: record findings, reclassify them, and attach evidence (spec 4.9)."""

import getpass

from textual.binding import Binding

from qa_workbench.bughunt.schema import CLASSIFICATIONS, SUSPECTED
from qa_workbench.bughunt.service import BugError, reclassify, record_finding
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_results import BUG_COLUMNS, bug_detail, bug_rows
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.file_dialog import FileDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

NEW_FIELDS = (
    FormField("title", "Title", "Checkout button does nothing", required=True),
    FormField("environment", "Environment and version", "staging 1.4.0", required=True),
    FormField("found_by", "Found by", required=True),
    FormField("steps", "Steps (separate with ;)", "Open the cart; Press Pay"),
    FormField("expected", "Expected result", "The payment page opens"),
    FormField("observed", "Observed result", "Nothing happens"),
)


def _number(text: str) -> int | None:
    return int(text) if text.strip().isdigit() else None


@register("bug-hunting")
class BugHuntingPage(BrowserPage):
    noun = "finding"
    columns = BUG_COLUMNS
    empty_message = "No findings yet."
    empty_hint = "Press N to record one. A defect needs evidence to be confirmed."
    shortcuts_hint = "N new   C reclassify   E attach evidence"

    BINDINGS = [
        Binding("n", "new_finding", "New"),
        Binding("c", "reclassify", "Reclassify"),
        Binding("e", "attach_evidence", "Evidence"),
    ]

    def load(self) -> BrowseData:
        return bug_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return bug_detail(self.context.repository(), key)

    # -- a new finding -----------------------------------------------------------

    def action_new_finding(self) -> None:
        if self.writable_project() is None:
            return
        fields = tuple(
            FormField(
                f.key,
                f.label,
                f.placeholder,
                f.required,
                getpass.getuser() if f.key == "found_by" else f.default,
            )
            for f in NEW_FIELDS
        )
        created: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                record = record_finding(
                    self.context.repository(),
                    title=values["title"],
                    environment=values["environment"],
                    found_by=values["found_by"],
                    classification=SUSPECTED,
                    steps=[s for s in values["steps"].split(";") if s.strip()],
                    expected=values["expected"],
                    observed=values["observed"],
                )
            except (BugError, StorageError) as error:
                return str(error)
            created.append(record.id)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None or not created:
                return
            self.refresh_data()
            self.app.notify(
                f"{created[0]} recorded as suspected. Attach evidence with E, then "
                "reclassify with C once it reproduces.",
                title="Finding",
                timeout=8,
            )

        self.app.push_screen(
            FormDialog("New finding", fields, submit_label="Record", commit=commit),
            done,
        )

    # -- reclassify ----------------------------------------------------------------

    def action_reclassify(self) -> None:
        bug_id = self.selected_key()
        if self.writable_project() is None or bug_id is None:
            return

        def picked(classification: str | None) -> None:
            if classification is not None:
                self._ask_why(bug_id, classification)

        self.app.push_screen(
            ChoiceDialog(
                f"Reclassify {bug_id}",
                list(CLASSIFICATIONS),
                note="A confirmed defect (reproduced) needs evidence, steps, "
                "expected and observed results, and two reproductions.",
            ),
            picked,
        )

    def _ask_why(self, bug_id: str, classification: str) -> None:
        fields = (
            FormField("by", "Your name", required=True, default=getpass.getuser()),
            FormField("why", "Why", required=True),
            FormField("attempts", "Times tried (optional)", "3"),
            FormField("reproductions", "Times it happened (optional)", "2"),
            FormField("reason", "Reason (false positive / environment problem)"),
        )
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                record = reclassify(
                    self.context.repository(),
                    bug_id,
                    classification,
                    by=values["by"],
                    justification=values["why"],
                    attempts=_number(values["attempts"]),
                    reproductions=_number(values["reproductions"]),
                    reason=values["reason"],
                )
            except (BugError, StorageError) as error:
                return str(error)
            outcome.append(f"{record.id} is now {record.metadata['status']}.")
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None or not outcome:
                return
            self.refresh_data()
            self.app.notify(outcome[0], title="Finding")

        self.app.push_screen(
            FormDialog(
                f"{bug_id} -> {classification}",
                fields,
                submit_label="Reclassify",
                commit=commit,
            ),
            done,
        )

    # -- evidence ------------------------------------------------------------------

    def action_attach_evidence(self) -> None:
        bug_id = self.selected_key()
        if self.writable_project() is None or bug_id is None:
            return

        def chosen(path) -> None:
            if path is not None:
                self._describe_evidence(bug_id, path)

        self.app.push_screen(FileDialog(f"Evidence for {bug_id}"), chosen)

    def _describe_evidence(self, bug_id: str, path) -> None:
        fields = (
            FormField("description", "What it shows", required=True),
            FormField("source", "Where it came from", required=True, default="manual"),
        )
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            repository = self.context.repository()
            try:
                record = EvidenceStore(repository).register(
                    path, source=values["source"], description=values["description"]
                )
                current = repository.get(bug_id)
                linked = [*current.metadata.get("evidence", []), record.id]
                repository.update(bug_id, {"evidence": linked})
            except (StorageError, ValueError, OSError) as error:
                return str(error)
            sha = record.metadata["sha256"][:12]
            outcome.append(f"{record.id} (sha256 {sha}...) is attached to {bug_id}.")
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None or not outcome:
                return
            self.refresh_data()
            self.app.notify(outcome[0], title="Evidence", timeout=8)

        self.app.push_screen(
            FormDialog(
                f"Evidence {path.name}",
                fields,
                submit_label="Attach",
                commit=commit,
            ),
            done,
        )
