"""Test suites: browse them, create one, add and remove cases (spec 4.5)."""

from textual.binding import Binding

from qa_workbench.storage.errors import StorageError
from qa_workbench.suites.schema import TYPES
from qa_workbench.suites.service import (
    SuiteError,
    add_cases,
    create_suite,
    remove_cases,
)
from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_planning import SUITE_COLUMNS, suite_detail, suite_rows
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

NEW_SUITE_FIELDS = (
    FormField("title", "Title", "Smoke", required=True),
    FormField("type", "Type", "smoke, regression, api, custom ...", required=True),
    FormField("description", "Description", "Essential application flows"),
    FormField("cases", "Test cases (TC ids, comma separated)", "TC-001, TC-002"),
)
CASES_FIELD = (
    FormField("cases", "Test cases (TC ids, comma separated)", "TC-001", True),
)


def split_ids(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def validate_new_suite(values: dict[str, str]) -> str | None:
    if values["type"] not in TYPES:
        return f"Type must be one of: {', '.join(sorted(TYPES))}."
    return None


@register("test-suites")
class SuitesPage(BrowserPage):
    noun = "suite"
    columns = SUITE_COLUMNS
    empty_message = "No suites yet."
    empty_hint = "Press N to group test cases into the first one."
    shortcuts_hint = "N new   A add cases   R remove cases"

    BINDINGS = [
        Binding("n", "new_suite", "New"),
        Binding("a", "add_cases", "Add"),
        Binding("r", "remove_cases", "Remove"),
    ]

    def load(self) -> BrowseData:
        return suite_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return suite_detail(self.context.repository(), key)

    def action_new_suite(self) -> None:
        if self.writable_project() is None:
            return

        def commit(values: dict[str, str]) -> str | None:
            try:
                create_suite(
                    self.context.repository(),
                    values["title"],
                    values["type"],
                    description=values["description"],
                    cases=split_ids(values["cases"]),
                )
            except (SuiteError, StorageError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify(f"Suite '{values['title']}' created as a draft.")

        self.app.push_screen(
            FormDialog(
                "New suite",
                NEW_SUITE_FIELDS,
                submit_label="Create",
                validate=validate_new_suite,
                commit=commit,
            ),
            done,
        )

    def _change_cases(self, title: str, change, verb: str) -> None:
        suite_id = self.selected_key()
        if self.writable_project() is None:
            return
        if suite_id is None:
            self.app.notify("Select a suite first.", severity="warning")
            return

        def commit(values: dict[str, str]) -> str | None:
            try:
                change(self.context.repository(), suite_id, split_ids(values["cases"]))
            except (SuiteError, StorageError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify(f"{suite_id}: cases {verb}.")

        self.app.push_screen(
            FormDialog(
                f"{title} {suite_id}", CASES_FIELD, submit_label=title, commit=commit
            ),
            done,
        )

    def action_add_cases(self) -> None:
        self._change_cases("Add cases to", add_cases, "added")

    def action_remove_cases(self) -> None:
        self._change_cases("Remove cases from", remove_cases, "removed")
