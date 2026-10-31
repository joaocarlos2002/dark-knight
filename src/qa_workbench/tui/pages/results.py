"""Read-only pages for saved results: defects, API runs, and release analyses."""

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
    empty_hint = "Run a definition with `batman api run FILE.yaml -p PROJ`."

    def load(self) -> BrowseData:
        return api_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return api_detail(self.context.repository(), key)


@register("release-analysis")
class ReleaseAnalysisPage(BrowserPage):
    noun = "analysis"
    columns = RELEASE_COLUMNS
    empty_message = "No release analyses yet."
    empty_hint = "Create one with `batman release analyze -p PROJ`."

    def load(self) -> BrowseData:
        return release_rows(self.context.repository())

    def describe(self, key: str) -> str:
        return release_detail(self.context.repository(), key)
