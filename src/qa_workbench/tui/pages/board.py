"""Board: a group board column across every project, and an issue's links."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Static

from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.gitlab.board import (
    GitLabBoard,
    GitLabIssueLinks,
    GroupIssue,
)
from qa_workbench.integrations.gitlab.client import (
    DEFAULT_TOKEN_ENV,
    GitLabClient,
    GitLabConnection,
)
from qa_workbench.integrations.gitlab.wiki import group_of
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."
HINT = "Nothing is fetched until you ask: press R to read a board column."
COLUMNS = ("Issue", "State", "Title", "Labels")
FIELDS = (
    FormField(
        "labels",
        "Labels (filter label, column label)",
        "team::dev,workflow::QA",
        required=True,
    ),
    FormField("only", "Only this project (path, optional)", "nees/app/frontend"),
)


@register("board")
class BoardPage(Page):
    """A column is read on demand, in a worker, and kept only in memory."""

    BINDINGS = [
        Binding("r", "fetch", "Read"),
        Binding("l", "links", "Links"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._issues: dict[str, GroupIssue] = {}
        self._selected: str | None = None
        self._labels: tuple[str, ...] = ()
        self._only = ""

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="board-summary", markup=False)
        yield DataTable(
            COLUMNS,
            empty_message="No issues loaded.",
            empty_hint=HINT,
            id="board-table",
        )
        with VerticalScroll(id="browse-detail-box"):
            yield Static("", id="board-detail", markup=False)

    def focus_primary(self) -> None:
        table = self.query_one("#board-table").query_one(TextualDataTable)
        table.focus() if table.display else self.focus()

    def refresh_data(self) -> None:
        if self.context.project is None:
            self._summary(NO_PROJECT)
        elif not self._issues:
            self._summary(HINT)

    def _summary(self, text: str) -> None:
        self.query_one("#board-summary", Static).update(text)

    # -- reading -----------------------------------------------------------------

    def _client(self, what: str) -> tuple[GitLabClient, str]:
        """The client, after the guard allows the read; and the group."""
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
        ActionGuard(load_settings(root), AuditLog(root)).authorize(
            ActionRequest(
                f"read board {what}",
                Category.READ,
                f"{what} of the group of {connection.project_path}",
                target_url=connection.base_url,
                requested_by="tui",
            )
        )
        client = GitLabClient(connection, gitlab_cli.default_gateway())
        return client, group_of(connection.project_path)

    def _start(self, what: str, work, done) -> None:
        try:
            client, group = self._client(what)
        except (
            IntegrationError,
            SecurityError,
            AuditError,
            SecuritySettingsError,
        ) as error:
            self._summary(f"{format_status(Status.FAILED)}  {error}")
            return
        if not group:
            self._summary(f"{format_status(Status.FAILED)}  The project has no group.")
            return
        self._summary(f"Reading {what} ...")

        def run() -> None:
            try:
                result = work(client, group)
            except IntegrationError as error:
                self.app.call_from_thread(self._failed, str(error))
            else:
                self.app.call_from_thread(done, result)

        self.run_worker(run, thread=True, exclusive=True, group="board")

    def _failed(self, message: str) -> None:
        self._summary(f"{format_status(Status.FAILED)}  {message}")

    # -- actions -----------------------------------------------------------------

    def action_fetch(self) -> None:
        if self.context.project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return

        def chosen(values: dict[str, str] | None) -> None:
            if values is None:
                return
            self._labels = tuple(
                part.strip() for part in values["labels"].split(",") if part.strip()
            )
            self._only = values["only"].strip()
            self._start(
                "the board column",
                lambda client, group: GitLabBoard(client, group).column(
                    self._labels, project=self._only
                ),
                self._loaded,
            )

        self.app.push_screen(
            FormDialog("Board column", FIELDS, submit_label="Read"), chosen
        )

    def _loaded(self, issues: list[GroupIssue]) -> None:
        self._issues = {i.reference: i for i in issues}
        table = self.query_one("#board-table", DataTable)
        table.set_rows(
            [
                (i.reference, (i.reference, i.state, i.title, ", ".join(i.labels)))
                for i in issues
            ]
        )
        self._summary(
            f"{len(issues)} issue(s) with {', '.join(self._labels) or 'any label'}"
            f"   R read   L links"
        )
        self.query_one("#board-detail", Static).update(
            "" if issues else "No issue carries all of those labels."
        )
        if issues:
            self.focus_primary()

    def action_links(self) -> None:
        issue = self._issues.get(self._selected or "")
        if issue is None:
            return
        project = self.context.project
        assert project is not None
        base = GitLabConnection.from_repository_url(
            project.repository, token_env=DEFAULT_TOKEN_ENV
        ).base_url

        def work(client: GitLabClient, group: str):
            other = GitLabClient(
                GitLabConnection(base, issue.project, DEFAULT_TOKEN_ENV),
                gitlab_cli.default_gateway(),
            )
            return GitLabIssueLinks(other).links(issue.iid)

        self._start(
            "the issue's links", work, lambda links: self._links_loaded(issue, links)
        )

    def _links_loaded(self, issue: GroupIssue, links) -> None:
        lines = [f"{issue.reference}  {issue.title}", f"{issue.url}", ""]
        lines += [
            f"{link.kind:<22} {link.reference}  {link.state}  {link.title}"
            for link in links
        ] or ["This issue has no links."]
        self.query_one("#board-detail", Static).update("\n".join(lines))
        self._summary(f"Links of {issue.reference}")

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        self._selected = event.key
        issue = self._issues.get(event.key or "")
        if issue is not None:
            who = ", ".join(issue.assignees) or "-"
            self.query_one("#board-detail", Static).update(
                f"{issue.reference}  {issue.title}\n{issue.url}\n"
                f"Assigned to {who}\nPress L to read its links."
            )
