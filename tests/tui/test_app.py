import asyncio
from collections.abc import Awaitable, Callable

import pytest
from textual.widgets import OptionList, Static

from qa_workbench.tui.app import WorkbenchApp


def _run(
    size: tuple[int, int], scenario: Callable[[WorkbenchApp, object], Awaitable[None]]
) -> None:
    async def runner() -> None:
        app = WorkbenchApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


def _visible(app: WorkbenchApp) -> dict[str, bool]:
    return {
        region: app.query_one(f"#{region}").display
        for region in ("sidebar", "main", "context")
    }


def test_wide_terminal_shows_all_regions() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert _visible(app) == {"sidebar": True, "main": True, "context": True}
        assert "-wide" in app.screen.classes

    _run((140, 40), scenario)


def test_medium_terminal_hides_context_until_requested() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert _visible(app) == {"sidebar": True, "main": True, "context": False}
        await pilot.press("f2")
        assert app.query_one("#context").display

    _run((100, 40), scenario)


def test_narrow_terminal_shows_content_and_opens_menu_on_demand() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert _visible(app) == {"sidebar": False, "main": True, "context": False}
        await pilot.press("f1")
        assert _visible(app) == {"sidebar": True, "main": False, "context": False}

    _run((60, 40), scenario)


def test_short_terminal_is_flagged() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert "-short" in app.screen.classes

    _run((140, 20), scenario)


def test_resize_reclassifies_the_layout() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.resize_terminal(60, 40)
        await pilot.pause()
        assert "-narrow" in app.screen.classes
        assert not app.query_one("#sidebar").display

    _run((140, 40), scenario)


def test_keyboard_navigation_changes_the_page() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert str(app.query_one("#page-title", Static).render()) == "OVERVIEW"
        await pilot.press("down", "enter")
        assert str(app.query_one("#page-title", Static).render()) == "REQUIREMENTS"

    _run((140, 40), scenario)


def test_narrow_menu_closes_after_choosing_a_page() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("f1")
        await pilot.press("down", "enter")
        assert _visible(app) == {"sidebar": False, "main": True, "context": False}

    _run((60, 40), scenario)


def test_unavailable_module_is_not_reported_as_working() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        body = str(app.query_one("#page-body", Static).render())
        assert "PENDING" in body
        assert "not available yet" in body

    _run((140, 40), scenario)


def test_status_bar_names_state_without_relying_on_color() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        text = str(app.query_one("#status-bar", Static).render())
        assert "● READY" in text

    _run((140, 40), scenario)


def test_section_headers_are_not_selectable() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        sidebar = app.query_one("#sidebar", OptionList)
        headers = [option for option in sidebar.options if option.id is None]
        assert headers
        assert all(option.disabled for option in headers)

    _run((140, 40), scenario)


@pytest.mark.parametrize("size", [(140, 40), (100, 40), (60, 40)])
def test_help_shortcut_does_not_break_the_shell(size: tuple[int, int]) -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("question_mark")
        assert app.is_running

    _run(size, scenario)
