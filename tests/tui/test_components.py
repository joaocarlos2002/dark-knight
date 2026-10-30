import asyncio
from collections.abc import Awaitable, Callable

import pytest
from textual.app import App, ComposeResult
from textual.widget import Widget

from qa_workbench.tui.components.badge import StatusBadge
from qa_workbench.tui.components.detail import DetailPanel, format_fields
from qa_workbench.tui.components.metric import MetricPanel, format_metric
from qa_workbench.tui.components.states import EmptyState, ErrorState, LoadingState
from qa_workbench.tui.status import Status
from qa_workbench.tui.theme import SHELL_CSS


def _show(widget: Widget, check: Callable[[Widget], Awaitable[None]]) -> None:
    class Host(App[None]):
        CSS = SHELL_CSS

        def compose(self) -> ComposeResult:
            yield widget

    async def runner() -> None:
        app = Host()
        async with app.run_test(size=(80, 20)) as pilot:
            await pilot.pause()
            await check(widget)

    asyncio.run(runner())


def _text(widget: Widget) -> str:
    return str(widget.render())


def test_badge_shows_symbol_and_name() -> None:
    async def check(widget: Widget) -> None:
        assert _text(widget) == "✓ PASSED"
        assert widget.has_class("tone-success")

    _show(StatusBadge(Status.PASSED), check)


def test_badge_changes_status_and_tone() -> None:
    badge = StatusBadge(Status.RUNNING)

    async def check(widget: Widget) -> None:
        assert isinstance(widget, StatusBadge)
        widget.set_status(Status.FAILED)
        assert _text(widget) == "✗ FAILED"
        assert widget.has_class("tone-error")
        assert not widget.has_class("tone-info")

    _show(badge, check)


def test_blocked_badge_is_not_styled_as_an_error() -> None:
    async def check(widget: Widget) -> None:
        assert not widget.has_class("tone-error")

    _show(StatusBadge(Status.BLOCKED), check)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(128, "128"), (0, "0"), (12.345, "12.3"), ("2h", "2h"), (None, "n/a")],
)
def test_metric_formatting(value: int | float | str | None, expected: str) -> None:
    assert format_metric(value) == expected


def test_missing_metric_is_not_shown_as_zero() -> None:
    async def check(widget: Widget) -> None:
        assert _text(widget) == "PASSED\nn/a"

    _show(MetricPanel("passed", None), check)


def test_metric_panel_updates_its_value() -> None:
    async def check(widget: Widget) -> None:
        assert isinstance(widget, MetricPanel)
        widget.set_value(102)
        assert _text(widget) == "PASSED\n102"

    _show(MetricPanel("Passed", 5), check)


def test_metric_panel_requires_a_label() -> None:
    with pytest.raises(ValueError, match="needs a label"):
        MetricPanel("  ", 1)


def test_detail_fields_are_aligned_and_blank_values_are_marked() -> None:
    text = format_fields([("Project", "Shop"), ("Env", ""), ("Repository", " ")])

    assert text.splitlines() == [
        "Project     Shop",
        "Env         -",
        "Repository  -",
    ]


def test_detail_panel_shows_title_and_fields() -> None:
    async def check(widget: Widget) -> None:
        assert _text(widget) == "TC-001\n\nStatus  active"

    _show(DetailPanel("tc-001", [("Status", "active")]), check)


def test_detail_panel_requires_a_title() -> None:
    with pytest.raises(ValueError, match="needs a title"):
        DetailPanel("", [])


def test_empty_state_explains_the_next_step() -> None:
    async def check(widget: Widget) -> None:
        assert _text(widget) == "No projects yet.\nRun: qa-workbench project create"

    _show(EmptyState("No projects yet.", "Run: qa-workbench project create"), check)


def test_empty_state_requires_a_message() -> None:
    with pytest.raises(ValueError, match="needs a message"):
        EmptyState(" ")


def test_loading_state_is_static_text() -> None:
    async def check(widget: Widget) -> None:
        assert _text(widget) == "● RUNNING  Loading"

    _show(LoadingState(), check)


def test_error_state_keeps_the_diagnostic_context() -> None:
    async def check(widget: Widget) -> None:
        text = _text(widget)
        assert "✗ FAILED  Cannot open project" in text
        assert "Invalid project record C:/data/project.yaml" in text
        assert "Next step: fix the file and retry" in text
        assert widget.has_class("state-error")

    _show(
        ErrorState(
            "Cannot open project",
            "Invalid project record C:/data/project.yaml",
            "fix the file and retry",
        ),
        check,
    )


@pytest.mark.parametrize(("title", "detail"), [("", "x"), ("x", ""), (" ", " ")])
def test_error_state_requires_title_and_detail(title: str, detail: str) -> None:
    with pytest.raises(ValueError, match="needs a title and a detail"):
        ErrorState(title, detail)
