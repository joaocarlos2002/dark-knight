"""GitLab: issues, merge requests, and commits of the project, read on demand."""

import getpass
from dataclasses import dataclass

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
from qa_workbench.integrations.gitlab.issues import GitLabIssues
from qa_workbench.integrations.gitlab.repository import GitLabRepository
from qa_workbench.integrations.untrusted import fence
from qa_workbench.publishing.service import CommentError, GitLabComments, draft_comment
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."
HINT = "Nothing is fetched until you ask: press R to choose what to read."
KINDS = ("Issues", "Merge requests", "Commits")
COLUMNS = ("Ref", "State", "Title", "Detail")
LIMIT = 30


def _branches(mr) -> str:
    return mr.source_branch + " -> " + mr.target_branch


@dataclass(frozen=True)
class Row:
    key: str
    cells: tuple[str, str, str, str]


@register("gitlab")
class GitLabPage(Page):
    """What is read stays in memory only: it is the server's current word."""

    BINDINGS = [
        Binding("r", "fetch", "Read"),
        Binding("c", "draft_comment", "Draft comment"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._kind = ""
        self._rows: dict[str, Row] = {}
        self._selected: str | None = None
        self._client: GitLabClient | None = None
        self._base = ""

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="gl-summary", markup=False)
        yield DataTable(
            COLUMNS,
            empty_message="Nothing loaded.",
            empty_hint=HINT,
            id="gl-table",
        )
        with VerticalScroll(id="browse-detail-box"):
            yield Static("", id="gl-detail", markup=False)

    def focus_primary(self) -> None:
        table = self.query_one("#gl-table").query_one(TextualDataTable)
        table.focus() if table.display else self.focus()

    def refresh_data(self) -> None:
        if self.context.project is None:
            self._summary(NO_PROJECT)
        elif not self._rows:
            self._summary(HINT)

    def _summary(self, text: str) -> None:
        self.query_one("#gl-summary", Static).update(text)

    # -- connecting --------------------------------------------------------------

    def _connect(self, what: str) -> GitLabClient:
        """The client, after the guard allows the read."""
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
                f"read {what}",
                Category.READ,
                f"{what} of {connection.project_path}",
                target_url=connection.base_url,
                requested_by="tui",
            )
        )
        self._base = connection.base_url
        return GitLabClient(connection, gitlab_cli.default_gateway())

    def _start(self, what: str, work, done) -> None:
        try:
            client = self._connect(what)
        except (
            IntegrationError,
            SecurityError,
            AuditError,
            SecuritySettingsError,
        ) as error:
            self._summary(f"{format_status(Status.FAILED)}  {error}")
            return
        self._client = client
        self._summary(f"Reading {what} ...")

        def run() -> None:
            try:
                result = work(client)
            except IntegrationError as error:
                self.app.call_from_thread(self._failed, str(error))
            else:
                self.app.call_from_thread(done, result)

        self.run_worker(run, thread=True, exclusive=True, group="gitlab")

    def _failed(self, message: str) -> None:
        self._summary(f"{format_status(Status.FAILED)}  {message}")

    # -- listing -----------------------------------------------------------------

    def action_fetch(self) -> None:
        if self.context.project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return

        def chosen(kind: str | None) -> None:
            if kind is None:
                return
            self._kind = kind
            self._start(kind.lower(), self._reader(kind), self._loaded)

        self.app.push_screen(ChoiceDialog("Read from GitLab", list(KINDS)), chosen)

    @staticmethod
    def _reader(kind: str):
        def read(client: GitLabClient) -> list[Row]:
            if kind == "Issues":
                return [
                    Row(
                        str(i.iid),
                        (f"#{i.iid}", i.state, i.title, ", ".join(i.labels) or "-"),
                    )
                    for i in GitLabIssues(client).list_issues(limit=LIMIT)
                ]
            repository = GitLabRepository(client)
            if kind == "Merge requests":
                return [
                    Row(
                        str(m.iid),
                        (
                            f"!{m.iid}",
                            m.state,
                            m.title,
                            f"{m.source_branch} -> {m.target_branch}",
                        ),
                    )
                    for m in repository.list_merge_requests(limit=LIMIT)
                ]
            return [
                Row(c.sha, (c.sha[:8], "-", c.title, c.author or "-"))
                for c in repository.list_commits(limit=LIMIT)
            ]

        return read

    def _loaded(self, rows: list[Row]) -> None:
        self._rows = {r.key: r for r in rows}
        self.query_one("#gl-table", DataTable).set_rows(
            [(r.key, r.cells) for r in rows]
        )
        self._summary(
            f"{len(rows)} {self._kind.lower()} from {self._base}   R read   "
            "C draft comment"
        )
        self.query_one("#gl-detail", Static).update(
            "" if rows else f"GitLab returned no {self._kind.lower()}."
        )
        if rows:
            self.focus_primary()

    # -- detail ------------------------------------------------------------------

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        self._selected = event.key
        if event.key is None or event.key not in self._rows or self._client is None:
            return
        key, kind, client = event.key, self._kind, self._client

        def read(client: GitLabClient) -> str:
            if kind == "Issues":
                issue = GitLabIssues(client).get_issue(int(key))
                text = fence(
                    f"{issue.title}\n\n{issue.description}",
                    source=f"GitLab issue #{key}",
                )
                comments = [
                    fence(n.body, source=f"comment by {n.author}")
                    for n in issue.notes
                    if not n.system
                ]
                return "\n\n".join(
                    [f"#{key} {issue.state}  {issue.url}", text, *comments]
                )
            repository = GitLabRepository(client)
            if kind == "Merge requests":
                mr = repository.get_merge_request(int(key))
                files = "\n".join(f"  {f}" for f in mr.files) or "  (none)"
                title = fence(mr.title, source=f"GitLab merge request !{key}")
                return f"!{key} {mr.state}  {mr.url}\n{title}\nFiles changed:\n{files}"
            commit = repository.get_commit(key)
            files = "\n".join(f"  {f}" for f in commit.files) or "  (none)"
            title = fence(commit.title, source=f"GitLab commit {key[:8]}")
            return f"{key}\n{title}\nFiles changed:\n{files}"

        def work() -> None:
            try:
                text = read(client)
            except IntegrationError as error:
                text = f"{format_status(Status.FAILED)}  {error}"
            self.app.call_from_thread(self._show_detail, key, text)

        self.run_worker(work, thread=True, exclusive=True, group="gitlab-detail")

    def _show_detail(self, key: str, text: str) -> None:
        if self._selected == key:
            self.query_one("#gl-detail", Static).update(text)

    # -- drafting a comment ------------------------------------------------------

    def action_draft_comment(self) -> None:
        project = self.context.project
        if project is None or project.archived:
            self.app.notify(
                "Open a project that can be changed first.", severity="warning"
            )
            return
        if self._kind != "Issues" or self._selected is None:
            self.app.notify("Read the issues and select one first.", severity="warning")
            return
        issue = int(self._selected)
        records = EvidenceStore(self.context.repository()).list_records().records
        if not records:
            self.app.notify(
                "A comment must cite evidence. Add some on the Evidence page first.",
                severity="warning",
                title="Comment",
            )
            return
        labels = {
            f"{r.id}  {r.metadata.get('description', '')}"[:70]: r.id for r in records
        }

        def picked(label: str | None) -> None:
            if label is not None:
                self._ask_comment(project, issue, labels[label])

        self.app.push_screen(
            ChoiceDialog(
                "Evidence that supports the comment",
                list(labels),
                note="A comment on an issue always cites the evidence behind it.",
            ),
            picked,
        )

    def _ask_comment(self, project, issue: int, evidence: str) -> None:
        fields = (
            FormField("author", "Your name", required=True, default=getpass.getuser()),
            FormField("body", "Comment", required=True),
        )
        outcome: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            root = self.context.repository()
            try:
                connection = GitLabConnection.from_repository_url(
                    project.repository, token_env=DEFAULT_TOKEN_ENV
                )
                writer = GitLabComments(
                    GitLabClient(connection, gitlab_cli.default_gateway()),
                    connection.base_url,
                    connection.project_path,
                )
                record = draft_comment(
                    root,
                    issue=issue,
                    body=values["body"],
                    author=values["author"],
                    writer=writer,
                    allowed_hosts=load_settings(root.root).allowed_hosts,
                    evidence=[evidence],
                )
            except (
                CommentError,
                IntegrationError,
                SecuritySettingsError,
                StorageError,
            ) as error:
                return str(error)
            outcome.append(
                f"{record.id} drafted. Nothing was sent: publish it from Comments."
            )
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None and outcome:
                self.app.notify(outcome[0], title="Comment", timeout=10)

        self.app.push_screen(
            FormDialog(
                f"Comment on issue #{issue}",
                fields,
                submit_label="Draft",
                commit=commit,
            ),
            done,
        )
