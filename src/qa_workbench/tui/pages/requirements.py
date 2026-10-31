"""Requirements: browse them, see their coverage, and import more (spec 4.2)."""

from pathlib import Path

from textual.binding import Binding

from qa_workbench.requirements.importer import (
    RequirementImportError,
    import_requirements,
)
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse import (
    REQUIREMENT_COLUMNS,
    BrowseData,
    requirement_detail,
    requirement_rows,
)
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


@register("requirements")
class RequirementsPage(BrowserPage):
    noun = "requirement"
    columns = REQUIREMENT_COLUMNS
    empty_message = "No requirements yet."
    empty_hint = "Press I to import them from a Markdown or text file."
    shortcuts_hint = "I import"

    BINDINGS = [Binding("i", "import_requirements", "Import")]

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
