"""Review: the records the AI made, waiting for a person's decision (REQ-013)."""

import getpass

from textual.binding import Binding

from qa_workbench.review.policy import APPROVED, CHANGES_REQUESTED, REJECTED
from qa_workbench.review.service import ReviewError
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_review import (
    REVIEW_COLUMNS,
    review_detail,
    review_rows,
    review_service,
)
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

TITLES = {
    APPROVED: "Approve",
    REJECTED: "Reject",
    CHANGES_REQUESTED: "Ask for changes",
}


def decision_fields(decision: str) -> tuple[FormField, ...]:
    needs_reason = decision != APPROVED
    return (
        FormField("reviewer", "Your name", required=True, default=getpass.getuser()),
        FormField(
            "comment",
            "Why" + (" (required)" if needs_reason else " (optional)"),
            required=needs_reason,
        ),
    )


@register("review")
class ReviewPage(BrowserPage):
    noun = "record"
    columns = REVIEW_COLUMNS
    empty_message = "Nothing is waiting for review."
    empty_hint = "Records the AI creates arrive here as drafts."
    shortcuts_hint = "S submit   A approve   X reject   C changes"

    BINDINGS = [
        *BrowserPage.BINDINGS,
        Binding("s", "submit", "Submit"),
        Binding("a", "approve", "Approve"),
        Binding("x", "reject", "Reject"),
        Binding("c", "changes", "Changes"),
    ]

    def load(self) -> BrowseData:
        return review_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return review_detail(self.context.repository(), key)

    # -- actions -----------------------------------------------------------------

    def action_submit(self) -> None:
        record_id = self.selected_key()
        if self.writable_project() is None or record_id is None:
            return
        try:
            record = review_service(self.context.repository()).submit(record_id)
        except (ReviewError, StorageError) as error:
            self.app.notify(str(error), severity="error", title="Not submitted")
            return
        self.refresh_data()
        self.app.notify(f"{record.id} is now {record.metadata['status']}.")

    def action_approve(self) -> None:
        self._decide(APPROVED)

    def action_reject(self) -> None:
        self._decide(REJECTED)

    def action_changes(self) -> None:
        self._decide(CHANGES_REQUESTED)

    def _decide(self, decision: str) -> None:
        record_id = self.selected_key()
        if self.writable_project() is None or record_id is None:
            return
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                record = review_service(self.context.repository()).decide(
                    record_id, values["reviewer"], decision, values["comment"]
                )
            except (ReviewError, StorageError, ValueError) as error:
                return str(error)
            outcome.append(f"{record.id} is now {record.metadata['status']}.")
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None or not outcome:
                return
            self.refresh_data()
            self.app.notify(outcome[0], title=TITLES[decision])

        self.app.push_screen(
            FormDialog(
                f"{TITLES[decision]} {record_id}",
                decision_fields(decision),
                submit_label=TITLES[decision],
                commit=commit,
            ),
            done,
        )
