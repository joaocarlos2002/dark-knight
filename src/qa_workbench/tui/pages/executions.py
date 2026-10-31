"""Executions: follow them, start one, and move it through its lifecycle (spec 4.6)."""

from textual.binding import Binding

from qa_workbench.executions.schema import EXECUTION_TYPES, FAILURE_TYPES
from qa_workbench.executions.service import ExecutionError, create_execution, move
from qa_workbench.executions.states import InvalidTransition
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_executions import (
    EXECUTION_COLUMNS,
    allowed_moves,
    execution_detail,
    execution_rows,
)
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

NEW_FIELDS = (
    FormField("case", "Test case (TC id)", "TC-001", required=True),
    FormField("type", "Type", "manual", required=True, default="manual"),
    FormField("executor", "Executor", "Ana", required=True),
    FormField("environment", "Environment", "staging", required=True),
    FormField("version", "Version", "1.4.0"),
)


def split_ids(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def validate_new(values: dict[str, str]) -> str | None:
    if values["type"] not in EXECUTION_TYPES:
        return f"Type must be one of: {', '.join(sorted(EXECUTION_TYPES))}."
    return None


@register("executions")
class ExecutionsPage(BrowserPage):
    noun = "execution"
    columns = EXECUTION_COLUMNS
    empty_message = "No executions yet."
    empty_hint = "Press N to start one from a test case."
    shortcuts_hint = "N new   M move to the next state"

    BINDINGS = [
        Binding("n", "new_execution", "New"),
        Binding("m", "move_execution", "Move"),
    ]

    def load(self) -> BrowseData:
        return execution_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return execution_detail(self.context.repository(), key)

    def action_new_execution(self) -> None:
        if self.writable_project() is None:
            return

        def commit(values: dict[str, str]) -> str | None:
            try:
                create_execution(
                    self.context.repository(),
                    execution_type=values["type"],
                    executor=values["executor"],
                    environment=values["environment"],
                    test_case=values["case"],
                    version=values["version"] or None,
                )
            except (ExecutionError, StorageError, ValueError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify("Execution created. Select it and press M to start.")

        self.app.push_screen(
            FormDialog(
                "New execution",
                NEW_FIELDS,
                submit_label="Create",
                validate=validate_new,
                commit=commit,
            ),
            done,
        )

    def action_move_execution(self) -> None:
        execution_id = self.selected_key()
        if self.writable_project() is None:
            return
        if execution_id is None:
            self.app.notify("Select an execution first.", severity="warning")
            return
        options = allowed_moves(self.context.repository(), execution_id)
        if not options:
            self.app.notify(f"{execution_id} is final and cannot change.")
            return
        fields = (
            FormField("target", f"Move to ({', '.join(options)})", options[0], True),
            FormField("observed", "Observed result (for a result state)", ""),
            FormField(
                "failure",
                f"Failure type, if failed ({', '.join(sorted(FAILURE_TYPES))})",
                "product",
            ),
            FormField("evidence", "Evidence (EVD ids, comma separated)", "EVD-001"),
            FormField("reason", "Reason (for blocked or cancelled)", ""),
            FormField("approver", "Approved by (when approval is required)", ""),
        )

        def validate(values: dict[str, str]) -> str | None:
            if values["target"] not in options:
                return f"From here an execution can move to: {', '.join(options)}."
            return None

        def commit(values: dict[str, str]) -> str | None:
            try:
                move(
                    self.context.repository(),
                    execution_id,
                    values["target"],
                    observed_result=values["observed"] or None,
                    reason=values["reason"] or None,
                    evidence=split_ids(values["evidence"]),
                    failure_type=values["failure"] or None,
                    approved_by=values["approver"] or None,
                )
            except (
                ExecutionError,
                InvalidTransition,
                StorageError,
                ValueError,
            ) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify(f"{execution_id} is now {values['target']}.")

        self.app.push_screen(
            FormDialog(
                f"Move {execution_id}",
                fields,
                submit_label="Move",
                validate=validate,
                commit=commit,
            ),
            done,
        )
