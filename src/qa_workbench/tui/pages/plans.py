"""Test plans: browse them and write a new one (spec 4.4)."""

from textual.binding import Binding

from qa_workbench.plans.builder import PlanDraft, create_plan
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_planning import PLAN_COLUMNS, plan_detail, plan_rows
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage

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


class PlansPage(BrowserPage):
    noun = "plan"
    columns = PLAN_COLUMNS
    empty_message = "No test plans yet."
    empty_hint = "Press N to write the first one."
    shortcuts_hint = "N new"

    BINDINGS = [Binding("n", "new_plan", "New")]

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
