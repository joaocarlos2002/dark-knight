import pytest

from qa_workbench.tui import navigation
from qa_workbench.tui.pages import PAGES, Page, register


def test_every_registered_page_is_a_navigation_destination() -> None:
    keys = {item.key for item in navigation.all_items()}

    assert set(PAGES) <= keys
    assert all(issubclass(page, Page) for page in PAGES.values())


def test_the_pages_built_so_far_are_registered() -> None:
    assert {
        "overview",
        "projects",
        "requirements",
        "test-cases",
        "test-plans",
        "test-suites",
    } <= set(PAGES)


def test_two_pages_cannot_claim_the_same_destination() -> None:
    with pytest.raises(ValueError, match="Two pages claim"):

        @register("overview")
        class Another(Page):
            pass
