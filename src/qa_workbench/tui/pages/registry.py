"""Where pages register themselves by navigation key.

A page module decorates its class with ``@register("key")``; the package imports
every module in ``tui/pages/`` so adding a page means adding one file, with no
central list to edit.
"""

from collections.abc import Callable
from dataclasses import dataclass

from qa_workbench.tui.pages.base import Page

PAGES: dict[str, type[Page]] = {}
SHELL_ONLY_PAGES = frozenset({"browser-preview"})


@dataclass(frozen=True)
class ScreenContract:
    """The implementation contract shared by a navigable screen."""

    key: str
    page_class: type[Page]

    @property
    def supports_search(self) -> bool:
        """Whether the screen exposes the shared search affordance."""
        return self.page_class.screen_kind == "browser"

    @property
    def supports_filter(self) -> bool:
        """Whether the screen exposes the shared status filter shortcut."""
        return any(
            binding.action == "cycle_filter" for binding in self.page_class.BINDINGS
        )

    @property
    def supports_detail(self) -> bool:
        """Whether the screen has a selected-record detail view."""
        return self.page_class.screen_kind == "browser"


def register(key: str) -> Callable[[type[Page]], type[Page]]:
    """Register a page class for the navigation destination ``key``."""

    def decorate(page_class: type[Page]) -> type[Page]:
        if key in PAGES:
            raise ValueError(f"Two pages claim the destination {key!r}.")
        PAGES[key] = page_class
        return page_class

    return decorate


def screen_contracts() -> dict[str, ScreenContract]:
    """Return the contracts for every registered implementation."""
    return {key: ScreenContract(key, page_class) for key, page_class in PAGES.items()}


def validate_screen_contracts(navigation_keys: set[str]) -> None:
    """Reject navigation/implementation drift instead of showing false screens."""
    registered = set(PAGES)
    missing = navigation_keys - registered - SHELL_ONLY_PAGES
    orphaned = registered - navigation_keys
    if missing or orphaned:
        details = []
        if missing:
            details.append(f"missing pages: {', '.join(sorted(missing))}")
        if orphaned:
            details.append(f"orphaned pages: {', '.join(sorted(orphaned))}")
        raise ValueError("Invalid TUI screen contracts: " + "; ".join(details))
