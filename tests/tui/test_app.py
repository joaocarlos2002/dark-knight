import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from textual.widgets import OptionList, Static

from qa_workbench.projects.models import Environment, Project
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.keymap import Keymap


def _run(
    size: tuple[int, int], scenario: Callable[[WorkbenchApp, object], Awaitable[None]]
) -> None:
    async def runner() -> None:
        app = WorkbenchApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


_REGIONS = {"sidebar": "#navigation", "main": "#main", "context": "#context"}


def _visible(app: WorkbenchApp) -> dict[str, bool]:
    return {name: app.query_one(query).display for name, query in _REGIONS.items()}


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

    _run((90, 40), scenario)


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
        assert not app.query_one("#navigation").display

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


def _unbuilt_page() -> str:
    """A destination that has no page yet, whichever pages exist today."""
    from qa_workbench.tui import navigation
    from qa_workbench.tui.pages import PAGES

    special = {"browser-preview"}  # the app draws this one itself
    return next(
        i.key for i in navigation.all_items() if i.key not in {*PAGES, *special}
    )


def test_unavailable_module_is_not_reported_as_working() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        app.navigate(_unbuilt_page())
        body = str(app.query_one("#page-body", Static).render())
        assert "PENDING" in body
        assert "not available yet" in body

    _run((140, 40), scenario)


def test_status_bar_names_state_without_relying_on_color() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        footer = str(app.query_one("#footer-identity", Static).render())
        assert "SYSTEM STATUS: ● OPERATIONAL" in footer

    _run((140, 40), scenario)


def test_section_headers_are_not_selectable() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        sidebar = app.query_one("#sidebar", OptionList)
        headers = [option for option in sidebar.options if option.id is None]
        assert headers
        assert all(option.disabled for option in headers)

    _run((140, 40), scenario)


@pytest.mark.parametrize("size", [(140, 40), (90, 40), (60, 40)])
def test_help_shortcut_does_not_break_the_shell(size: tuple[int, int]) -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("question_mark")
        assert app.is_running

    _run(size, scenario)


def _project() -> Project:
    now = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    return Project(
        id="PROJ-007",
        name="Shop",
        repository="acme/shop",
        environments=[Environment(name="staging", url="https://s.example.com")],
        created_at=now,
        updated_at=now,
    )


def _run_with(project: Project, scenario) -> None:
    async def runner() -> None:
        app = WorkbenchApp(project)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


def test_opened_project_is_shown_in_header_status_bar_and_context() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        header = str(app.query_one("#header-project", Static).render())
        status = str(app.query_one("#status-bar", Static).render())
        context = str(app.query_one("#context", Static).render())
        assert header == "PROJ-007 / SHOP"
        assert status.startswith("PROJ-007 │")
        assert "staging" in context
        assert "acme/shop" in context

    _run_with(_project(), scenario)


def test_without_a_project_the_shell_says_so() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert str(app.query_one("#header-project", Static).render()) == "NO PROJECT"
        assert str(app.query_one("#status-bar", Static).render()).startswith(
            "No project"
        )

    _run((140, 40), scenario)


def _title(app: WorkbenchApp) -> str:
    return str(app.query_one("#page-title", Static).render())


def test_palette_opens_with_ctrl_p_and_navigates() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("ctrl+p")
        await pilot.pause()
        await pilot.press(*"pipelines")
        await pilot.pause(0.5)
        await pilot.press("enter")
        await pilot.pause()
        assert _title(app) == "PIPELINES"
        sidebar = app.query_one("#sidebar", OptionList)
        assert sidebar.highlighted_option is not None
        assert sidebar.highlighted_option.id == "pipelines"

    _run((140, 40), scenario)


def test_escape_closes_the_context_drawer_on_medium_terminals() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("f2")
        assert app.query_one("#context").display
        await pilot.press("escape")
        assert not app.query_one("#context").display

    _run((90, 40), scenario)


def test_escape_closes_the_menu_on_narrow_terminals() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("f1")
        assert app.query_one("#navigation").display
        await pilot.press("escape")
        assert not app.query_one("#navigation").display
        assert app.query_one("#main").display

    _run((60, 40), scenario)


def test_escape_leaves_a_wide_layout_untouched() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("escape")
        assert _visible(app) == {"sidebar": True, "main": True, "context": True}

    _run((140, 40), scenario)


def test_focus_search_without_a_search_field_says_so() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert any("no search field" in n.message for n in app._notifications)

    _run((140, 40), scenario)


def test_custom_shortcut_replaces_the_default() -> None:
    keymap = Keymap.from_overrides({"toggle_context": "f3"})

    async def runner() -> None:
        app = WorkbenchApp(keymap=keymap)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await pilot.press("f2")
            assert app.query_one("#context").display
            await pilot.press("f3")
            assert not app.query_one("#context").display

    asyncio.run(runner())


def test_status_bar_shows_the_effective_shortcuts() -> None:
    keymap = Keymap.from_overrides({"toggle_context": "f3"})

    async def runner() -> None:
        app = WorkbenchApp(keymap=keymap)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            assert "F3 Context" in str(app.query_one("#status-bar", Static).render())

    asyncio.run(runner())


def test_a_100_column_terminal_shows_all_three_areas() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert _visible(app) == {"sidebar": True, "main": True, "context": True}

    _run((100, 40), scenario)


def test_header_and_footer_carry_the_wayne_industries_identity() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        def text(query: str) -> str:
            return str(app.query_one(query, Static).render())

        assert text("#header-company") == "WAYNE INDUSTRIES"
        assert text("#header-division") == "ADVANCED TECHNOLOGY DIVISION"
        assert text("#header-location") == "INTERNAL SYSTEM / GOTHAM CITY"
        assert text("#brand") == "DARK KNIGHT QA\nQUALITY INTELLIGENCE SYSTEM"
        footer = text("#footer-identity")
        assert "WAYNE INDUSTRIES / INTERNAL SOFTWARE" in footer
        assert "AUTHORIZED ACCESS ONLY" in footer

    _run((140, 40), scenario)


def test_secondary_identity_lines_are_hidden_on_short_terminals() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        assert "-short" in app.screen.classes
        assert not app.query_one("#header-row-2").display
        assert not app.query_one("#footer-identity").display
        assert app.query_one("#header-company").display
        assert app.query_one("#status-bar").display

    _run((140, 20), scenario)


def test_navigation_labels_are_uppercase() -> None:
    async def scenario(app: WorkbenchApp, pilot) -> None:
        sidebar = app.query_one("#sidebar", OptionList)
        labels = [str(option.prompt) for option in sidebar.options]
        assert labels[0] == "WORKSPACE"
        assert "OVERVIEW" in labels
        assert all(label == label.upper() for label in labels)

    _run((140, 40), scenario)
