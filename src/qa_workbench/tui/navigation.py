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
        "EXECUTION",
        (
            NavItem("test-execution", "Test Execution"),
            NavItem("browser-agent", "Browser Agent"),
            NavItem("automation", "Automation"),
        ),
    ),
    NavSection(
        "ANALYSIS",
        (
            NavItem("issue-testing", "Issue Testing"),
            NavItem("bug-hunting", "Bug Hunting"),
            NavItem("release-analysis", "Release Analysis"),
        ),
    ),
    NavSection(
        "INTEGRATIONS",
        (
            NavItem("pipelines", "Pipelines"),
            NavItem("issues", "Issues"),
            NavItem("api-testing", "API Testing"),
            NavItem("security", "Security"),
        ),
    ),
    NavSection(
        "SYSTEM",
        (
            NavItem("reports", "Reports"),
            NavItem("knowledge", "Knowledge"),
            NavItem("ai-agent", "AI Agent"),
            NavItem("settings", "Settings"),
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
