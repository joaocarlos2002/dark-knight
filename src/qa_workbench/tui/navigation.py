"""Navigation model for the workbench sidebar."""

from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    """One destination in the sidebar."""

    key: str
    title: str


@dataclass(frozen=True)
class NavSection:
    """A titled group of destinations."""

    title: str
    items: tuple[NavItem, ...]


SECTIONS: tuple[NavSection, ...] = (
    NavSection(
        "WORKSPACE",
        (
            NavItem("overview", "Overview"),
            NavItem("requirements", "Requirements"),
            NavItem("test-cases", "Test Cases"),
            NavItem("test-plans", "Test Plans"),
            NavItem("test-suites", "Test Suites"),
        ),
    ),
    NavSection(
        "OPERATIONS",
        (
            NavItem("executions", "Executions"),
            NavItem("browser-preview", "Browser Preview"),
            NavItem("bug-hunting", "Bug Hunting"),
            NavItem("api-testing", "API Testing"),
            NavItem("security", "Security"),
        ),
    ),
    NavSection(
        "INTELLIGENCE",
        (
            NavItem("ai-agent", "AI Agent"),
            NavItem("release-analysis", "Release Analysis"),
            NavItem("pipelines", "Pipelines"),
            NavItem("knowledge-base", "Knowledge Base"),
        ),
    ),
)

DEFAULT_KEY = "overview"


def all_items() -> tuple[NavItem, ...]:
    """Return every destination in display order."""
    return tuple(item for section in SECTIONS for item in section.items)


def find_item(key: str) -> NavItem:
    """Return the destination for a key, rejecting unknown keys."""
    for item in all_items():
        if item.key == key:
            return item
    raise KeyError(f"Unknown navigation destination: {key!r}.")
