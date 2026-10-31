"""The pages of the workbench, by navigation key."""

from qa_workbench.tui.pages.base import Page, PageContext
from qa_workbench.tui.pages.overview import OverviewPage
from qa_workbench.tui.pages.projects import ProjectsPage

PAGES: dict[str, type[Page]] = {
    "overview": OverviewPage,
    "projects": ProjectsPage,
}

__all__ = ["PAGES", "Page", "PageContext"]
