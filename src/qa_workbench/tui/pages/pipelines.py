"""Pipelines: recent CI pipelines and their jobs, read from GitLab (spec 4.11)."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Static

from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.gitlab.client import (
    DEFAULT_TOKEN_ENV,
    GitLabClient,
    GitLabConnection,
)
from qa_workbench.integrations.gitlab.pipelines import GitLabPipelines
from qa_workbench.integrations.models import Job, Pipeline
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.tui.browse_pipelines import (
    PIPELINE_COLUMNS,
    pipeline_cells,
    pipeline_detail,
)
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."
HINT = "Nothing is fetched until you ask: press R to read the latest pipelines."
LIMIT = 20


@register("pipelines")
class PipelinesPage(Page):
    """Pipelines are read on demand (``R``), in a worker thread, and kept only in
    memory: they are the server's current word, not a record of this project."""

    BINDINGS = [Binding("r", "fetch", "Fetch")]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pipelines: dict[int, Pipeline] = {}
        self._jobs: dict[int, list[Job]] = {}
        self._selected: int | None = None
        self._source: GitLabPipelines | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="pipe-summary", markup=False)
        yield DataTable(
            PIPELINE_COLUMNS,
            empty_message="No pipelines loaded.",
            empty_hint=HINT,
            id="pipe-table",
        )
        with VerticalScroll(id="pipe-detail-box"):
            yield Static("", id="pipe-detail", markup=False)

    def focus_primary(self) -> None:
        table = self.query_one("#pipe-table").query_one(TextualDataTable)
        table.focus() if table.display else self.focus()

    def refresh_data(self) -> None:
        if self.context.project is None:
            self._summary(NO_PROJECT)
        elif not self._pipelines:
            self._summary(HINT)

    def _summary(self, text: str) -> None:
        self.query_one("#pipe-summary", Static).update(text)

    # -- fetching ------------------------------------------------------------------

    def _connect(self) -> tuple[GitLabPipelines, str]:
        """The GitLab reader for this project, after the guard allows the read."""
        project = self.context.project
        assert project is not None
        if not project.repository:
            raise IntegrationError(
                "GitLab",
                f"{project.id} has no repository URL",
                hint="Set one when creating the project",
            )
        connection = GitLabConnection.from_repository_url(
            project.repository, token_env=DEFAULT_TOKEN_ENV
        )
        root = self.context.repository().root
        guard = ActionGuard(load_settings(root), AuditLog(root))
        guard.authorize(
            ActionRequest(
                "read pipelines",
                Category.READ,
                f"latest {LIMIT} pipelines of {connection.project_path}",
                target_url=connection.base_url,
                requested_by="tui",
            )
        )
        client = GitLabClient(connection, gitlab_cli.default_gateway())
        return GitLabPipelines(client), connection.base_url

    def action_fetch(self) -> None:
        if self.context.project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return
        try:
            source, host = self._connect()
        except (
            IntegrationError,
            SecurityError,
            AuditError,
            SecuritySettingsError,
        ) as error:
            self._summary(f"{format_status(Status.FAILED)}  {error}")
            return
        self._summary(f"Reading pipelines from {host} ...")

        def work() -> None:
            try:
                found = source.list_pipelines(limit=LIMIT)
            except IntegrationError as error:
                self.app.call_from_thread(self._failed, str(error))
            else:
                self.app.call_from_thread(self._loaded, found, host)

        self._source = source
        self.run_worker(work, thread=True, exclusive=True, group="pipelines")

    def _failed(self, message: str) -> None:
        self._summary(f"{format_status(Status.FAILED)}  {message}")

    def _loaded(self, pipelines: list[Pipeline], host: str) -> None:
        self._pipelines = {p.id: p for p in pipelines}
        self._jobs.clear()
        table = self.query_one("#pipe-table", DataTable)
        table.set_rows([(str(p.id), pipeline_cells(p)) for p in pipelines])
        self._summary(f"{len(pipelines)} pipeline(s) from {host}   R refresh")
        if not pipelines:
            self.query_one("#pipe-detail", Static).update(
                "GitLab returned no pipelines."
            )
        else:
            self.focus_primary()  # so the arrow keys move through the list

    # -- selection ------------------------------------------------------------------

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        if event.key is None or not event.key.isdigit():
            return
        self._select(int(event.key))

    def _select(self, pipeline_id: int) -> None:
        self._selected = pipeline_id
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            return
        jobs = self._jobs.get(pipeline_id)
        self.query_one("#pipe-detail", Static).update(pipeline_detail(pipeline, jobs))
        if jobs is not None:
            return
        source = self._source
        if source is None:
            return

        def work() -> None:
            try:
                loaded = source.list_jobs(pipeline_id)
            except IntegrationError as error:
                self.app.call_from_thread(self._jobs_failed, pipeline_id, str(error))
            else:
                self.app.call_from_thread(self._jobs_loaded, pipeline_id, loaded)

        self.run_worker(work, thread=True, exclusive=True, group="jobs")

    def _jobs_loaded(self, pipeline_id: int, jobs: list[Job]) -> None:
        self._jobs[pipeline_id] = jobs
        if self._selected == pipeline_id:
            pipeline = self._pipelines[pipeline_id]
            self.query_one("#pipe-detail", Static).update(
                pipeline_detail(pipeline, jobs)
            )

    def _jobs_failed(self, pipeline_id: int, message: str) -> None:
        if self._selected == pipeline_id:
            self.query_one("#pipe-detail", Static).update(
                f"{format_status(Status.FAILED)}  Jobs could not be read: {message}"
            )
