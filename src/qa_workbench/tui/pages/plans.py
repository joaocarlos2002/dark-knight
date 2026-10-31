"""Test plans: browse them and write a new one (spec 4.4)."""

from textual.binding import Binding

from qa_workbench.plans.builder import PlanDraft, create_plan
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_planning import PLAN_COLUMNS, plan_detail, plan_rows
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

NEW_PLAN_FIELDS = (
    FormField("title", "Title", "Release 1.5 campaign", required=True),
    FormField("scope", "Scope", "Login, registration, user management", required=True),
    FormField("strategy", "Strategy", "Smoke, then functional and regression", True),
    FormField(
        "objectives", "Objectives (separate with ;)", "Validate changed flows", True
    ),
    FormField("entry", "Entry criteria (separate with ;)", "Build deployed", True),
    FormField(
        "exit", "Exit criteria (separate with ;)", "No open critical defect", True
    ),
    FormField("suites", "Suites (SUITE ids, comma separated)", "SUITE-001"),
)


def split(text: str, separator: str) -> list[str]:
    return [part.strip() for part in text.split(separator) if part.strip()]


def draft_from(values: dict[str, str]) -> PlanDraft:
    return PlanDraft(
        title=values["title"],
        scope=values["scope"],
        strategy=values["strategy"],
        objectives=split(values["objectives"], ";"),
        entry_criteria=split(values["entry"], ";"),
        exit_criteria=split(values["exit"], ";"),
        suites=split(values["suites"], ","),
    )


@register("test-plans")
class PlansPage(BrowserPage):
    noun = "plan"
    columns = PLAN_COLUMNS
    empty_message = "No test plans yet."
    empty_hint = "Press N to write the first one."
    shortcuts_hint = "N new   E edit   D cancel"

    BINDINGS = [
        Binding("n", "new_plan", "New"),
        Binding("e", "edit_plan", "Edit"),
        Binding("d", "cancel_plan", "Cancel"),
    ]

    def load(self) -> BrowseData:
        return plan_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return plan_detail(self.context.repository(), key)

    def action_new_plan(self) -> None:
        if self.writable_project() is None:
            return

        def commit(values: dict[str, str]) -> str | None:
            repository = self.context.repository()
            draft = draft_from(values)
            known = set(repository.record_ids("SUITE"))
            unknown = [s for s in draft.suites if s not in known]
            if unknown:
                return f"Unknown suite(s): {', '.join(unknown)}."
            try:
                create_plan(repository, draft)
            except StorageError as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify(f"Plan '{values['title']}' created as a draft.")

        self.app.push_screen(
            FormDialog(
                "New test plan", NEW_PLAN_FIELDS, submit_label="Create", commit=commit
            ),
            done,
        )

    def action_edit_plan(self) -> None:
        plan_id = self.selected_key()
        if self.writable_project() is None or plan_id is None:
            return
        try:
            record = self.context.repository().get(plan_id)
        except StorageError as error:
            self.app.notify(str(error), severity="error")
            return
        meta = record.metadata

        def split(text: str, separator: str) -> list[str]:
            return [part.strip() for part in text.split(separator) if part.strip()]

        def commit(values: dict[str, str]) -> str | None:
            try:
                self.context.repository().update(
                    plan_id,
                    {
                        "title": values["title"],
                        "scope": values["scope"],
                        "strategy": values["strategy"] or None,
                        "objectives": split(values["objectives"], ";"),
                        "entry_criteria": split(values["entry"], ";"),
                        "exit_criteria": split(values["exit"], ";"),
                        "suites": split(values["suites"], ","),
                    },
                )
            except (StorageError, ValueError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify(f"{plan_id} updated.")

        obj_text = "; ".join(meta.get("objectives", []))
        entry_text = "; ".join(meta.get("entry_criteria", []))
        exit_text = "; ".join(meta.get("exit_criteria", []))
        suites_text = ", ".join(meta.get("suites", []))

        self.app.push_screen(
            FormDialog(
                f"Edit {plan_id}",
                (
                    FormField("title", "Title", required=True, default=meta["title"]),
                    FormField("scope", "Scope", required=True, default=meta["scope"]),
                    FormField(
                        "strategy",
                        "Strategy",
                        default=meta.get("strategy", ""),
                    ),
                    FormField(
                        "objectives", "Objectives (separate with ;)", default=obj_text
                    ),
                    FormField(
                        "entry", "Entry criteria (separate with ;)", default=entry_text
                    ),
                    FormField(
                        "exit", "Exit criteria (separate with ;)", default=exit_text
                    ),
                    FormField(
                        "suites",
                        "Suites (SUITE ids, comma separated)",
                        default=suites_text,
                    ),
                ),
                submit_label="Save",
                commit=commit,
            ),
            done,
        )

    def action_cancel_plan(self) -> None:
        plan_id = self.selected_key()
        if self.writable_project() is None or plan_id is None:
            return

        def done(result: bool | None) -> None:
            if not result:
                return
            try:
                self.context.repository().update(plan_id, {"status": "cancelled"})
            except (StorageError, ValueError) as error:
                self.app.notify(str(error), severity="error")
                return
            self.refresh_data()
            self.app.notify(f"{plan_id} cancelled.")

        self.app.push_screen(
            ConfirmationDialog(
                f"Cancel {plan_id}?",
                "Set status to 'cancelled'. This action can be undone by editing.",
            ),
            done,
        )
