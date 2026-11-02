"""Security: approval requests (decide them here), security checks, the audit log."""

import getpass

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
from qa_workbench.tui.runs import (
    RunFailed,
    authorization_text,
    grant_authorization,
    revoke_authorization,
    run_security_checks,
)

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
    empty_hint = "Risky actions ask here. U authorizes security checks, T runs them."
    shortcuts_hint = "A approve   D deny   U authorize   T run checks   K revoke"

    BINDINGS = [
        *BrowserPage.BINDINGS,
        Binding("a", "approve", "Approve"),
        Binding("d", "deny", "Deny"),
        Binding("u", "authorize_checks", "Authorize"),
        Binding("t", "run_checks", "Run checks"),
        Binding("k", "revoke_checks", "Revoke"),
    ]

    def load(self) -> BrowseData:
        return security_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return security_detail(self.context.repository(), key)

    def summary_suffix(self) -> str:
        repository = self.context.repository()
        return f"   {audit_summary(repository)}\n{authorization_text(repository)}"

    # -- authorized security checks -------------------------------------------

    def action_authorize_checks(self) -> None:
        if self.writable_project() is None:
            return
        fields = (
            FormField("by", "Who authorizes", required=True, default=getpass.getuser()),
            FormField("purpose", "What the tests are for", required=True),
            FormField("host", "Exact host to test", "staging.example.com", True),
            FormField("days", "Valid for (days, at most 30)", default="1"),
        )
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                days = float(values["days"] or "1")
                outcome.append(
                    grant_authorization(
                        self.context.repository(),
                        by=values["by"],
                        purpose=values["purpose"],
                        host=values["host"],
                        days=days,
                    )
                )
            except (RunFailed, ValueError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None and outcome:
                self.refresh_data()
                self.app.notify(outcome[0], title="Security tests")

        self.app.push_screen(
            FormDialog(
                "Authorize security tests",
                fields,
                submit_label="Authorize",
                commit=commit,
            ),
            done,
        )

    def action_revoke_checks(self) -> None:
        if self.writable_project() is None:
            return
        fields = (
            FormField("by", "Who revokes", required=True, default=getpass.getuser()),
        )
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                outcome.append(
                    revoke_authorization(self.context.repository(), by=values["by"])
                )
            except RunFailed as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None and outcome:
                self.refresh_data()
                self.app.notify(outcome[0], title="Security tests")

        self.app.push_screen(
            FormDialog(
                "Revoke the authorization", fields, submit_label="Revoke", commit=commit
            ),
            done,
        )

    def action_run_checks(self) -> None:
        if self.writable_project() is None:
            return
        fields = (
            FormField("url", "Target URL", "https://staging.example.com", True),
            FormField("paths", "Paths that need login (comma, optional)", "/admin"),
        )

        def done(values: dict[str, str] | None) -> None:
            if values is None:
                return
            repository = self.context.repository()
            paths = tuple(p.strip() for p in values["paths"].split(",") if p.strip())
            self.run_job(
                "Security checks",
                lambda: run_security_checks(
                    repository, values["url"], protected_paths=paths
                ),
            )

        self.app.push_screen(
            FormDialog("Run the authorized checks", fields, submit_label="Run"), done
        )

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
