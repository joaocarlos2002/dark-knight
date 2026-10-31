"""Comments: drafts for GitLab issues, published only with a person's approval."""

from textual.binding import Binding

from qa_workbench.core.config import ConfigurationError
from qa_workbench.integrations import errors as integration_errors
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.gitlab.client import (
    DEFAULT_TOKEN_ENV,
    GitLabClient,
    GitLabConnection,
)
from qa_workbench.projects.errors import ProjectError
from qa_workbench.publishing.service import (
    CommentError,
    GitLabComments,
    PublishFailed,
    publish_comment,
)
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, ApprovalRequired, SecurityError
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import BrowseData, BrowseRow
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

COLUMNS = ("ID", "Status", "Issue", "Author")


@register("comments")
class CommentsPage(BrowserPage):
    noun = "comment"
    columns = COLUMNS
    empty_message = "No comments yet."
    empty_hint = "Draft one from the GitLab page (select an issue, press C)."
    shortcuts_hint = "P publish (needs approval)"

    BINDINGS = [*BrowserPage.BINDINGS, Binding("p", "publish", "Publish")]

    def load(self) -> BrowseData:
        listing = self.context.repository().list_records("COMMENT")
        rows = []
        for record in listing.records:
            meta = record.metadata
            status = str(meta["status"])
            rows.append(
                BrowseRow(
                    record.id,
                    (record.id, status, f"#{meta['issue']}", str(meta["author"])),
                    status,
                    f"{record.id} {status} {meta['issue']} {meta['author']}".lower(),
                )
            )
        return BrowseData(tuple(rows), tuple(listing.errors))

    def describe(self, key: str) -> str:
        record = self.context.repository().get(key)
        meta = record.metadata
        lines = [
            f"{record.id}  {meta['status']}  {meta['issue_url']}",
            f"Author {meta['author']}   Evidence "
            f"{', '.join(meta.get('evidence', [])) or '-'}",
            "This is exactly what will be sent:",
            "",
            record.body.rstrip(),
        ]
        if meta.get("external_url"):
            lines += ["", f"Published: {meta['external_url']}"]
        return "\n".join(lines)

    def action_publish(self) -> None:
        comment_id = self.selected_key()
        project = self.writable_project()
        if project is None or comment_id is None:
            return
        self.app.notify(f"Publishing {comment_id}...", title="Comment")

        def work() -> None:
            repository = self.context.repository()
            try:
                meta = repository.get(comment_id).metadata
                connection = GitLabConnection.from_repository_url(
                    project.repository, token_env=DEFAULT_TOKEN_ENV
                )
                writer = GitLabComments(
                    GitLabClient(connection, gitlab_cli.default_gateway()),
                    connection.base_url,
                    connection.project_path,
                )
                guard = ActionGuard(
                    load_settings(repository.root), AuditLog(repository.root)
                )
                record = publish_comment(
                    repository, comment_id, guard=guard, writer=writer
                )
            except ApprovalRequired as error:
                message, bad = (
                    f"{error} Ask someone else to approve it on the Security page.",
                    True,
                )
            except PublishFailed as error:
                message, bad = f"{error} (recorded as {error.status})", True
            except (
                CommentError,
                SecurityError,
                AuditError,
                SecuritySettingsError,
                ConfigurationError,
                ProjectError,
                StorageError,
                integration_errors.IntegrationError,
                KeyError,
            ) as error:
                message, bad = str(error), True
            else:
                message, bad = f"Published {record.id}: {meta['issue_url']}", False
            self.app.call_from_thread(self._published, message, bad)

        self.run_worker(work, thread=True, exclusive=True, name="publish-comment")

    def _published(self, message: str, bad: bool) -> None:
        self.refresh_data()
        self.app.notify(
            message,
            title="Comment",
            severity="warning" if bad else "information",
            timeout=12,
        )
