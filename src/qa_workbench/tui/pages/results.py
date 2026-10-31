"""Read-only pages for saved results: defects, API runs, and release analyses."""

from textual.binding import Binding

from qa_workbench.tui.browse import BrowseData
from qa_workbench.tui.browse_results import (
    API_COLUMNS,
    RELEASE_COLUMNS,
    api_detail,
    api_rows,
    release_detail,
    release_rows,
)
from qa_workbench.tui.pages.browser import BrowserPage
from qa_workbench.tui.pages.registry import register


@register("api-testing")
class ApiTestingPage(BrowserPage):
    noun = "API run"
    columns = API_COLUMNS
    empty_message = "No API runs yet."
    empty_hint = "Press R to choose a definition file and run it."
    shortcuts_hint = "R run a definition"

    BINDINGS = [*BrowserPage.BINDINGS, Binding("r", "run_definition", "Run")]

    def action_run_definition(self) -> None:
        if self.writable_project() is None:
            return
        from qa_workbench.tui.components.file_dialog import FileDialog
        from qa_workbench.tui.runs import run_api_definition

        def chosen(path) -> None:
            if path is not None:
                repository = self.context.repository()
                self.run_job(
                    f"API run {path.name}",
                    lambda: run_api_definition(repository, path),
                )

        self.app.push_screen(FileDialog("API test definition (.yaml)"), chosen)

    def load(self) -> BrowseData:
        return api_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return api_detail(self.context.repository(), key)


@register("release-analysis")
class ReleaseAnalysisPage(BrowserPage):
    noun = "analysis"
    columns = RELEASE_COLUMNS
    empty_message = "No release analyses yet."
    empty_hint = "Press R to read the commits and merge requests and analyse them."
    shortcuts_hint = "R analyse"

    BINDINGS = [*BrowserPage.BINDINGS, Binding("r", "run_analysis", "Analyse")]

    def action_run_analysis(self) -> None:
        project = self.writable_project()
        if project is None:
            return
        from qa_workbench.tui.components.form import FormDialog, FormField
        from qa_workbench.tui.runs import run_release_analysis

        fields = (
            FormField("ref", "Branch, tag, or ref (empty: default branch)"),
            FormField("since", "Since (date, optional)", "2026-10-01"),
            FormField("limit", "Commits to read", "30", default="30"),
        )

        def done(values: dict[str, str] | None) -> None:
            if values is None:
                return
            repository = self.context.repository()
            limit = int(values["limit"]) if values["limit"].isdigit() else 30
            self.run_job(
                "Release analysis",
                lambda: run_release_analysis(
                    repository,
                    project.id,
                    self.context.data_dir,
                    ref=values["ref"] or None,
                    since=values["since"] or None,
                    limit=max(1, min(limit, 200)),
                ),
            )

        self.app.push_screen(
            FormDialog("Release analysis", fields, submit_label="Analyse"), done
        )

    def load(self) -> BrowseData:
        return release_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return release_detail(self.context.repository(), key)
