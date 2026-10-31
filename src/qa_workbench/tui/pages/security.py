"""Security: approval requests (decide them here), security checks, the audit log."""

from textual.binding import Binding

from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ApprovalBook, ApprovalError
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_results import (
    SECURITY_COLUMNS,
    audit_summary,
    security_detail,
    security_rows,
)
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

APPROVE_FIELDS = (
    FormField("by", "Your name", "Ana", required=True),
    FormField("reason", "Reason (optional)", "Looks right"),
)
DENY_FIELDS = (
    FormField("by", "Your name", "Ana", required=True),
    FormField("reason", "Reason", "Wrong environment", required=True),
)


@register("security")
class SecurityPage(BrowserPage):
    noun = "item"
    columns = SECURITY_COLUMNS
    empty_message = "No approval requests or security checks yet."
    empty_hint = "Risky actions ask here; run checks with `batman security-tests run`."
    shortcuts_hint = "A approve   D deny"

    BINDINGS = [
        Binding("a", "approve", "Approve"),
        Binding("d", "deny", "Deny"),
    ]

    def load(self) -> BrowseData:
        return security_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return security_detail(self.context.repository(), key)

    def summary_suffix(self) -> str:
        return f"   {audit_summary(self.context.repository())}"

    def _decide(self, approve: bool) -> None:
        key = self.selected_key()
        if self.writable_project() is None:
            return
        if key is None or not key.startswith("APR-"):
            self.app.notify("Select an approval request first.", severity="warning")
            return
        book = ApprovalBook(AuditLog(self.context.repository().root))
        current = book.get(key)
        if current is None or current.status != "pending":
            status = current.status if current else "unknown"
            self.app.notify(f"{key} is {status}; only pending requests can be decided.")
            return

        def commit(values: dict[str, str]) -> str | None:
            try:
                book.decide(
                    key, approve=approve, by=values["by"], reason=values["reason"]
                )
            except (ApprovalError, AuditError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                verdict = "approved" if approve else "denied"
                self.app.notify(f"{key} {verdict} by {values['by']}.")

        title = f"{'Approve' if approve else 'Deny'} {key}"
        self.app.push_screen(
            FormDialog(
                title,
                APPROVE_FIELDS if approve else DENY_FIELDS,
                submit_label="Approve" if approve else "Deny",
                commit=commit,
            ),
            done,
        )

    def action_approve(self) -> None:
        self._decide(True)

    def action_deny(self) -> None:
        self._decide(False)
