"""Where pages register themselves by navigation key.

A page module decorates its class with ``@register("key")``; the package imports
every module in ``tui/pages/`` so adding a page means adding one file, with no
central list to edit.
"""

from collections.abc import Callable

from qa_workbench.tui.pages.base import Page

PAGES: dict[str, type[Page]] = {}


def register(key: str) -> Callable[[type[Page]], type[Page]]:
    """Register a page class for the navigation destination ``key``."""

    def decorate(page_class: type[Page]) -> type[Page]:
        if key in PAGES:
            raise ValueError(f"Two pages claim the destination {key!r}.")
        PAGES[key] = page_class
        return page_class

    return decorate
