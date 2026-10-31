"""Test cases: browse them and write a new one (spec 4.3)."""

from textual.binding import Binding

from qa_workbench.storage.errors import StorageError
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.testcases.schema import PRIORITIES
from qa_workbench.tui.browse import CASE_COLUMNS, BrowseData, case_detail, case_rows
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage

NEW_CASE_FIELDS = (
    FormField("title", "Title", "Customer can log in", required=True),
    FormField(
        "objective", "Objective", "Validate login with valid data", required=True
    ),
    FormField(
        "steps",
        "Steps (separate with ;  use 'action => expected')",
        "Open the page => Form shown; Submit => Dashboard shown",
        required=True,
    ),
    FormField(
        "expected", "Expected result", "The user is authenticated", required=True
    ),
    FormField("priority", "Priority (high, medium, low)", "medium"),
    FormField("requirements", "Requirements (REQ ids, comma separated)", "REQ-001"),
)


def parse_steps(text: str) -> list[Step]:
    """``a => b; c`` becomes two steps; the part after ``=>`` is what to observe."""
    steps = []
    for part in text.split(";"):
        action, _, expected = part.partition("=>")
        if action.strip():
            steps.append(Step(action.strip(), expected.strip()))
    return steps


def draft_from(values: dict[str, str]) -> TestCaseDraft:
    return TestCaseDraft(
        title=values["title"],
        objective=values["objective"],
        steps=parse_steps(values["steps"]),
        expected_result=values["expected"],
        priority=values["priority"] or "medium",
        requirements=[
            r.strip() for r in values["requirements"].split(",") if r.strip()
        ],
    )


def validate_new_case(values: dict[str, str]) -> str | None:
    if values["priority"] and values["priority"] not in PRIORITIES:
        return f"Priority must be one of: {', '.join(sorted(PRIORITIES))}."
    if not parse_steps(values["steps"]):
        return "Give at least one step."
    return None


class TestCasesPage(BrowserPage):
    __test__ = False  # not a pytest test class

    noun = "test case"
    columns = CASE_COLUMNS
    empty_message = "No test cases yet."
    empty_hint = "Press N to write the first one."
    shortcuts_hint = "N new"

    BINDINGS = [Binding("n", "new_case", "New")]

    def load(self) -> BrowseData:
        return case_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return case_detail(self.context.repository(), key)

    def action_new_case(self) -> None:
        if self.writable_project() is None:
            return

        def commit(values: dict[str, str]) -> str | None:
            repository = self.context.repository()
            draft = draft_from(values)
            known = set(repository.record_ids("REQ"))
            unknown = [r for r in draft.requirements if r not in known]
            if unknown:
                return f"Unknown requirement(s): {', '.join(unknown)}."
            try:
                create_test_case(repository, draft)
            except StorageError as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None:
                return
            self.refresh_data()
            self.app.notify(f"Test case '{values['title']}' created as a draft.")

        self.app.push_screen(
            FormDialog(
                "New test case",
                NEW_CASE_FIELDS,
                submit_label="Create",
                validate=validate_new_case,
                commit=commit,
            ),
            done,
        )
