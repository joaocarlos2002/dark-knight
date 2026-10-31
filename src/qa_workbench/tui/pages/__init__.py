"""The pages of the workbench, by navigation key."""

from qa_workbench.tui.pages.base import Page, PageContext
from qa_workbench.tui.pages.cases import TestCasesPage
from qa_workbench.tui.pages.overview import OverviewPage
from qa_workbench.tui.pages.projects import ProjectsPage
from qa_workbench.tui.pages.requirements import RequirementsPage

PAGES: dict[str, type[Page]] = {
    "overview": OverviewPage,
    "projects": ProjectsPage,
    "requirements": RequirementsPage,
    "test-cases": TestCasesPage,
}

__all__ = ["PAGES", "Page", "PageContext"]
