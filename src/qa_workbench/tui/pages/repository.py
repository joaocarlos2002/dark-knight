"""Repository: browse the project's GitLab repository, read only (spec 4.11)."""

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
from qa_workbench.integrations.gitlab.files import GitLabFiles, TreeEntry
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open. Open Projects in the menu first."
HINT = "Nothing is fetched until you ask: press R to read the repository."
COLUMNS = ("Type", "Name")


@register("repository")
class RepositoryPage(Page):
    """Folders and files are read on demand, in a worker thread, and kept only in
    memory. File text is untrusted data and has secrets masked."""

    BINDINGS = [
        Binding("r", "fetch", "Read"),
        Binding("o", "open", "Open"),
        Binding("u", "up", "Up"),
        Binding("b", "branch", "Branch"),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._path = ""
        self._ref: str | None = None
        self._entries: dict[str, TreeEntry] = {}
        self._selected: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="repo-summary", markup=False)
        yield DataTable(
            COLUMNS,
            empty_message="Nothing loaded.",
            empty_hint=HINT,
            id="repo-table",
        )
        with VerticalScroll(id="browse-detail-box"):
            yield Static("", id="repo-detail", markup=False)

    def focus_primary(self) -> None:
        table = self.query_one("#repo-table").query_one(TextualDataTable)
        table.focus() if table.display else self.focus()

    def refresh_data(self) -> None:
        if self.context.project is None:
            self._summary(NO_PROJECT)
        elif not self._entries:
            self._summary(HINT)

    def _summary(self, text: str) -> None:
        self.query_one("#repo-summary", Static).update(text)

    def _where(self) -> str:
        return f"{self._ref or 'default branch'}:/{self._path}"

    # -- reading -----------------------------------------------------------------

    def _connect(self, what: str) -> tuple[GitLabFiles, str]:
        """The repository reader, after the guard allows the read."""
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
                f"read repository {what}",
                Category.READ,
                f"{what} of {connection.project_path}",
                target_url=connection.base_url,
                requested_by="tui",
            )
        )
        client = GitLabClient(connection, gitlab_cli.default_gateway())
        return GitLabFiles(client), connection.base_url

    def _start(self, what: str, work) -> None:
        if self.context.project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return
        try:
            source, host = self._connect(what)
        except (
            IntegrationError,
            SecurityError,
            AuditError,
            SecuritySettingsError,
        ) as error:
            self._summary(f"{format_status(Status.FAILED)}  {error}")
            return
        self._summary(f"Reading {what} from {host} ...")

        def run() -> None:
            try:
                result = work(source)
            except IntegrationError as error:
                self.app.call_from_thread(self._failed, str(error))
            else:
                self.app.call_from_thread(self._done, what, result, host)

        self.run_worker(run, thread=True, exclusive=True, group="repository")

    def _failed(self, message: str) -> None:
        self._summary(f"{format_status(Status.FAILED)}  {message}")

    def _done(self, what: str, result, host: str) -> None:
        if what == "branches":
            self._pick_branch(result)
        elif what == "file":
            self.query_one("#repo-detail", Static).update(
                f"{result.path} at {result.ref} ({result.size} bytes)\n"
                "Untrusted text, secrets masked.\n\n" + result.text
            )
            self._summary(f"{self._where()}   {host}")
        else:
            self._entries = {e.path: e for e in result}
            table = self.query_one("#repo-table", DataTable)
            rows = [(e.path, (e.kind, e.name)) for e in result]
            table.set_rows(rows)
            self._summary(f"{len(result)} entries   {self._where()}   {host}")
            self.query_one("#repo-detail", Static).update(
                "" if result else "This folder is empty."
            )
            if result:
                self.focus_primary()

    # -- actions -----------------------------------------------------------------

    def action_fetch(self) -> None:
        path, ref = self._path, self._ref
        self._start("folder", lambda source: source.list_tree(path, ref))

    def action_open(self) -> None:
        entry = self._entries.get(self._selected or "")
        if entry is None:
            return
        if entry.kind == "dir":
            self._path = entry.path
            self.action_fetch()
            return
        ref = self._ref
        self._start("file", lambda source: source.get_file(entry.path, ref))

    def action_up(self) -> None:
        self._path = self._path.rpartition("/")[0]
        self.action_fetch()

    def action_branch(self) -> None:
        self._start("branches", lambda source: source.list_branches())

    def _pick_branch(self, branches) -> None:
        if not branches:
            self.app.notify("The repository has no branches.", severity="warning")
            return
        names = [b.name for b in branches]

        def chosen(name: str | None) -> None:
            if name is not None:
                self._ref, self._path = name, ""
                self.action_fetch()

        self.app.push_screen(
            ChoiceDialog("Branch", names, current=self._ref or ""), chosen
        )

    def on_data_table_highlighted(self, event: DataTable.Highlighted) -> None:
        event.stop()
        self._selected = event.key
        entry = self._entries.get(event.key or "")
        if entry is not None:
            kind = "Folder" if entry.kind == "dir" else "File"
            self.query_one("#repo-detail", Static).update(
                f"{kind} {entry.path}\nPress O to open it."
            )
