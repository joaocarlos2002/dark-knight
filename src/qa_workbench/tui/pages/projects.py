"""Projects: choose the project to work on, create one, archive one."""

from pydantic import ValidationError
from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Static

from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.models import Environment
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.data import project_rows
from qa_workbench.tui.pages.base import Page

NEW_PROJECT_FIELDS = (
    FormField("name", "Name", "Checkout service", required=True),
    FormField("repository", "Repository URL", "https://gitlab.com/group/app"),
    FormField("environment", "Environment name", "staging"),
    FormField("url", "Environment URL", "https://staging.example.com"),
)


def validate_new_project(values: dict[str, str]) -> str | None:
    """Errors the dialog shows before anything is written."""
    if bool(values["environment"]) != bool(values["url"]):
        return "Give both the environment name and its URL, or neither."
    try:
        if values["environment"]:
            Environment(name=values["environment"], url=values["url"])
    except ValidationError as error:
        first = error.errors()[0]
        return str(first["msg"]).removeprefix("Value error, ")
    return None


class ProjectsPage(Page):
    BINDINGS = [
        Binding("n", "new_project", "New"),
        Binding("x", "archive_project", "Archive"),
    ]

    def compose(self) -> ComposeResult:
        yield Static(
            "Enter opens the selected project.   N new project   X archive",
            classes="page-hint",
        )
        yield DataTable(
            ["ID", "Name", "Status", "Environments", "Repository"],
            empty_message="No projects yet.",
            empty_hint="Press N to create the first one.",
            id="projects-table",
        )
        yield Static("", id="projects-problems", markup=False)

    def _repository(self) -> ProjectRepository:
        return ProjectRepository(self.context.data_dir)

    def refresh_data(self) -> None:
        listing = self._repository().list_projects(include_archived=True)
        rows = project_rows(listing)
        self.query_one("#projects-table", DataTable).set_rows(
            [
                (r.id, (r.id, r.name, r.status, r.environments, r.repository))
                for r in rows
            ]
        )
        problems = self.query_one("#projects-problems", Static)
        problems.update(
            "\n".join(f"Damaged project, not listed: {e}" for e in listing.errors)
        )

    def on_data_table_activated(self, event: DataTable.Activated) -> None:
        event.stop()
        self.app.open_project(event.key)  # type: ignore[attr-defined]

    def _selected_id(self) -> str | None:
        table = self.query_one("#projects-table DataTable", TextualDataTable)
        if table.row_count == 0:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return key

    def action_new_project(self) -> None:
        def done(values: dict[str, str] | None) -> None:
            if values is None:
                return
            environments = (
                [Environment(name=values["environment"], url=values["url"])]
                if values["environment"]
                else []
            )
            try:
                project = self._repository().create(
                    values["name"],
                    repository=values["repository"],
                    environments=environments,
                )
            except ProjectError as error:
                self.app.notify(
                    str(error), severity="error", title="Project not created"
                )
                return
            self.refresh_data()
            self.app.open_project(project.id)  # type: ignore[attr-defined]

        self.app.push_screen(
            FormDialog(
                "New project",
                NEW_PROJECT_FIELDS,
                submit_label="Create",
                validate=validate_new_project,
            ),
            done,
        )

    def action_archive_project(self) -> None:
        project_id = self._selected_id()
        if project_id is None:
            self.app.notify("There is no project to archive.", severity="warning")
            return

        def done(confirmed: bool | None) -> None:
            if not confirmed:
                return
            try:
                self._repository().archive(project_id)
            except ProjectError as error:
                self.app.notify(str(error), severity="error", title="Not archived")
                return
            self.refresh_data()
            self.app.project_archived(project_id)  # type: ignore[attr-defined]

        self.app.push_screen(
            ConfirmationDialog(
                "Archive project",
                f"Archive {project_id}? Its records stay on disk and can be read, "
                "but it can no longer be changed.",
                confirm_label="Archive",
                destructive=True,
            ),
            done,
        )
