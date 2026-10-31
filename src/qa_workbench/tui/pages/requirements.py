"""Requirements: browse them, see their coverage, and import more (spec 4.2)."""

from pathlib import Path

from textual.binding import Binding

from qa_workbench.core.config import ConfigurationError
from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.gitlab.connect import open_client, open_wiki
from qa_workbench.integrations.gitlab.wiki import DEFAULT_PREFIX
from qa_workbench.projects.errors import ProjectError
from qa_workbench.requirements.importer import (
    RequirementImportError,
    import_requirements,
)
from qa_workbench.requirements.wiki_import import import_wiki_pages
from qa_workbench.security.audit import AuditError
from qa_workbench.security.settings import SecuritySettingsError
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import (
    REQUIREMENT_COLUMNS,
    BrowseData,
    requirement_detail,
    requirement_rows,
)
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register

IMPORT_FIELDS = (
    FormField(
        "path", "File (.md or .txt)", "C:\\specs\\requirements.md", required=True
    ),
    FormField("author", "Author", "Ana"),
    FormField("version", "Source version", "v1.2"),
)

WIKI_FIELDS = (
    FormField("prefix", "Pages that start with", default=DEFAULT_PREFIX),
    FormField("group", "Group (empty: the project's group)", "nees/primeira-infancia"),
)

EDIT_REQ_FIELDS = (
    FormField("title", "Title", required=True),
    FormField("priority", "Priority (high, medium, low)", "medium"),
    FormField("status", "Status", "draft"),
    FormField("tags", "Tags (comma separated)", ""),
    FormField("acceptance_criteria", "Acceptance criteria (separate with ;)", ""),
)


@register("requirements")
class RequirementsPage(BrowserPage):
    noun = "requirement"
    columns = REQUIREMENT_COLUMNS
    empty_message = "No requirements yet."
    empty_hint = "Press I to import them from a Markdown or text file."
    shortcuts_hint = "I import   W wiki   E edit   D archive"

    BINDINGS = [
        Binding("i", "import_requirements", "Import"),
        Binding("w", "import_wiki", "Wiki"),
        Binding("e", "edit_requirement", "Edit"),
        Binding("d", "archive_requirement", "Archive"),
    ]

    def load(self) -> BrowseData:
        return requirement_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return requirement_detail(self.context.repository(), key)

    def action_import_requirements(self) -> None:
        project = self.writable_project()
        if project is None:
            return
        summary: list[str] = []

        def commit(values: dict[str, str]) -> str | None:
            try:
                report = import_requirements(
                    self.context.repository(),
                    Path(values["path"]).expanduser(),
                    author=values["author"] or None,
                    source_version=values["version"] or None,
                )
            except (RequirementImportError, StorageError, OSError) as error:
                return str(error)
            summary.append(
                f"{len(report.created)} imported, {len(report.skipped)} already "
                f"there, {len(report.issues)} problem(s)."
            )
            for issue in report.issues[:3]:
                summary.append(f"{issue.location}: {issue.message}")
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is None:
                return
            self.refresh_data()
            self.app.notify("\n".join(summary), title="Import finished", timeout=10)

        self.app.push_screen(
            FormDialog(
                "Import requirements",
                IMPORT_FIELDS,
                submit_label="Import",
                commit=commit,
            ),
            done,
        )

    def action_import_wiki(self) -> None:
        """Read the group wiki and import its requirement pages (in a worker)."""
        project = self.writable_project()
        if project is None:
            return

        def done(values: dict[str, str] | None) -> None:
            if values is None:
                return
            self.app.notify("Reading the wiki...", title="Wiki import")
            self.run_worker(
                lambda: self._import_wiki(project.id, values),
                thread=True,
                exclusive=True,
                name="wiki-import",
            )

        self.app.push_screen(
            FormDialog("GitLab wiki", WIKI_FIELDS, submit_label="Import"),
            done,
        )

    def _import_wiki(self, project_id: str, values: dict[str, str]) -> None:
        try:
            client = open_client(
                project_id,
                gitlab_cli.default_gateway(),
                data_dir=self.context.data_dir,
            )
            wiki, group = open_wiki(client, values["group"] or None)
            prefix = values["prefix"] or DEFAULT_PREFIX
            pages = wiki.list_pages(prefix, with_content=True)
            report = import_wiki_pages(
                self.context.repository(), pages, base_url=client.base_url, group=group
            )
        except (
            IntegrationError,
            ProjectError,
            ConfigurationError,
            AuditError,
            SecuritySettingsError,
            StorageError,
            OSError,
        ) as error:
            self.app.call_from_thread(self._wiki_failed, str(error))
            return
        lines = [
            f"{len(report.created)} created, {len(report.updated)} updated, "
            f"{len(report.skipped)} unchanged, {len(report.issues)} problem(s)."
        ]
        lines += [f"{i.location}: {i.message}" for i in report.issues[:3]]
        self.app.call_from_thread(self._wiki_done, "\n".join(lines))

    def _wiki_done(self, summary: str) -> None:
        self.refresh_data()
        self.app.notify(summary, title="Wiki import finished", timeout=10)

    def _wiki_failed(self, message: str) -> None:
        self.app.notify(
            message, severity="error", title="Wiki import failed", timeout=10
        )

    def action_edit_requirement(self) -> None:
        req_id = self.selected_key()
        if self.writable_project() is None or req_id is None:
            return
        try:
            self.context.repository().get(req_id)
        except StorageError as error:
            self.app.notify(str(error), severity="error")
            return

        def commit(values: dict[str, str]) -> str | None:
            try:
                self.context.repository().update(
                    req_id,
                    {
                        "title": values["title"],
                        "priority": values["priority"] or None,
                        "status": values["status"],
                        "tags": [
                            t.strip() for t in values["tags"].split(",") if t.strip()
                        ],
                        "acceptance_criteria": [
                            c.strip()
                            for c in values["acceptance_criteria"].split(";")
                            if c.strip()
                        ],
                    },
                )
            except (StorageError, ValueError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify(f"{req_id} updated.")

        self.app.push_screen(
            FormDialog(
                f"Edit {req_id}",
                EDIT_REQ_FIELDS,
                submit_label="Save",
                commit=commit,
            ),
            done,
        )

    def action_archive_requirement(self) -> None:
        req_id = self.selected_key()
        if self.writable_project() is None or req_id is None:
            return

        def done(result: bool | None) -> None:
            if not result:
                return
            try:
                self.context.repository().update(req_id, {"status": "obsolete"})
            except (StorageError, ValueError) as error:
                self.app.notify(str(error), severity="error")
                return
            self.refresh_data()
            self.app.notify(f"{req_id} archived.")

        self.app.push_screen(
            ConfirmationDialog(
                f"Archive {req_id}?",
                "Set status to 'obsolete'. This action can be undone by editing.",
            ),
            done,
        )
