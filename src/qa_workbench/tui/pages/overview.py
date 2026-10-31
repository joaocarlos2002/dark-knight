"""Overview: the state of the project's quality, from its records (spec 4.1)."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.components.metric import MetricPanel
from qa_workbench.tui.components.states import EmptyState
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.data import OverviewData, build_overview
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open."
NO_PROJECT_HINT = "Open Projects in the menu to create or select one."


def identity_text(data: OverviewData) -> str:
    project = data.project
    environments = ", ".join(f"{e.name} ({e.url})" for e in project.environments)
    return "\n".join(
        [
            f"Project      {project.name}  [{project.id}]",
            f"Repository   {project.repository or '-'}",
            f"Environments {environments or '-'}",
        ]
    )


class OverviewPage(Page):
    def compose(self) -> ComposeResult:
        yield Static("", id="overview-identity", markup=False)
        with Horizontal(id="overview-metrics"):
            yield MetricPanel("Test cases", None, id="metric-cases")
            yield MetricPanel("Passed", None, id="metric-passed")
            yield MetricPanel("Failed", None, id="metric-failed")
            yield MetricPanel("Blocked", None, id="metric-blocked")
            yield MetricPanel("In progress", None, id="metric-progress")
        yield Static("RECENT EXECUTIONS", classes="section-title")
        yield DataTable(
            ["ID", "Result", "Time", "Case"],
            empty_message="No executions yet.",
            empty_hint="Create one with `batman executions create`.",
            id="overview-recent",
        )
        yield Static("PIPELINES", classes="section-title")
        yield EmptyState(
            "No pipelines are recorded in this project.",
            "Inspect GitLab with `batman gitlab pipelines`.",
        )
        yield Static("", id="overview-problems", markup=False)
        yield EmptyState(NO_PROJECT, NO_PROJECT_HINT, id="overview-empty")

    def refresh_data(self) -> None:
        project = self.context.project
        has_project = project is not None
        self.query_one("#overview-empty").display = not has_project
        for selector in ("#overview-identity", "#overview-metrics", "#overview-recent"):
            self.query_one(selector).display = has_project
        if not has_project:
            return
        try:
            data = build_overview(self.context.repository(), project)
        except (StorageError, OSError, ValueError) as error:
            self.query_one("#overview-problems", Static).update(
                f"{format_status(Status.FAILED)}  The project's records could not "
                f"be read\n{error}\nNext step: check the project folder, then "
                "press Ctrl+R."
            )
            return
        self._show(data)

    def _show(self, data: OverviewData) -> None:
        self.query_one("#overview-identity", Static).update(identity_text(data))
        self.query_one("#metric-cases", MetricPanel).set_value(data.test_cases)
        for key in ("passed", "failed", "blocked"):
            self.query_one(f"#metric-{key}", MetricPanel).set_value(data.results[key])
        self.query_one("#metric-progress", MetricPanel).set_value(data.in_progress)
        self.query_one("#overview-recent", DataTable).set_rows(
            [
                (
                    row.id,
                    (
                        row.id,
                        format_status(row.status) if row.status else row.status_text,
                        row.duration,
                        row.case,
                    ),
                )
                for row in data.recent
            ]
        )
        problems = self.query_one("#overview-problems", Static)
        if data.problems:
            shown = "\n".join(f"  - {p}" for p in data.problems[:5])
            count = len(data.problems)
            problems.update(f"{count} damaged record(s) are not counted:\n{shown}")
        else:
            problems.update("")
