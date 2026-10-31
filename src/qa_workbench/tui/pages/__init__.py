"""The pages of the workbench, by navigation key."""

from qa_workbench.tui.pages.base import Page, PageContext
from qa_workbench.tui.pages.overview import OverviewPage

PAGES: dict[str, type[Page]] = {
    "overview": OverviewPage,
}

__all__ = ["PAGES", "Page", "PageContext"]
