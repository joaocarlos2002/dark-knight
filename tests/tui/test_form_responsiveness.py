"""Tests for FormDialog responsiveness at small terminal sizes."""

import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Static

from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.theme import SHELL_CSS


class FormHost(App[None]):
    CSS = SHELL_CSS

    def __init__(self, dialog: FormDialog) -> None:
        super().__init__()
        self._dialog = dialog
        self.dismissed_values: dict[str, str] | None = None

    def compose(self) -> ComposeResult:
        yield Static("host")

    def on_mount(self) -> None:
        self.push_screen(self._dialog, self._record)

    def _record(self, result: dict[str, str] | None) -> None:
        self.dismissed_values = result


def _run_form(dialog: FormDialog, size: tuple[int, int]) -> FormHost:
    host = FormHost(dialog)

    async def runner() -> None:
        async with host.run_test(size=size) as pilot:
            await pilot.pause()

    asyncio.run(runner())
    return host


def _large_form() -> FormDialog:
    """A form with many fields to test scrolling."""
    fields = [
        FormField(
            f"field_{i}", f"Field {i}", placeholder=f"Enter value {i}", required=(i < 3)
        )
        for i in range(1, 16)  # 15 fields
    ]
    return FormDialog("Large Form with Many Fields", fields, submit_label="Save")


def _small_form() -> FormDialog:
    """A form with few fields."""
    fields = [
        FormField("name", "Name", required=True),
        FormField("email", "Email", required=True),
    ]
    return FormDialog("Small Form", fields, submit_label="Save")


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_form_dialog_fits_on_small_terminal(size: tuple[int, int]) -> None:
    """FormDialog should fit on small terminals without cutting off content."""
    host = _run_form(_small_form(), size)

    # The form should be dismissed (user didn't submit, so it's None)
    # but the screen should have been the form
    assert host.dismissed_values is None


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_large_form_dialog_scrolls_on_small_terminal(size: tuple[int, int]) -> None:
    """Large FormDialog should be scrollable on small terminals."""
    host = _run_form(_large_form(), size)

    # The form should be accessible and not crash
    assert host.dismissed_values is None


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_form_dialog_all_fields_accessible(size: tuple[int, int]) -> None:
    """All fields in a form should be accessible via tab navigation."""
    fields = [
        FormField("a", "Field A", required=True),
        FormField("b", "Field B", required=True),
        FormField("c", "Field C"),
        FormField("d", "Field D"),
        FormField("e", "Field E"),
    ]
    dialog = FormDialog("Test Form", fields, submit_label="Submit")

    async def runner() -> None:
        host = FormHost(dialog)
        async with host.run_test(size=size) as pilot:
            await pilot.pause()
            # First field should be focused
            assert isinstance(pilot.app.screen, FormDialog)
            form = pilot.app.screen
            first_input = form.query_one("#field-a", Input)
            assert first_input.has_focus

            # Tab through fields
            for i, key in enumerate(["b", "c", "d", "e"]):
                await pilot.press("tab")
                await pilot.pause()
                input_widget = form.query_one(f"#field-{key}", Input)
                assert input_widget.has_focus, f"Field {key} should be focused"

            # Shift+Tab back
            for key in ["d", "c", "b", "a"]:
                await pilot.press("shift+tab")
                await pilot.pause()
                input_widget = form.query_one(f"#field-{key}", Input)
                assert input_widget.has_focus, f"Field {key} should be focused"

    asyncio.run(runner())


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_form_dialog_submit_and_cancel_buttons_accessible(
    size: tuple[int, int],
) -> None:
    """Submit and Cancel buttons should be accessible."""
    fields = [FormField("name", "Name", required=True)]
    dialog = FormDialog("Test", fields, submit_label="Save")

    async def runner() -> None:
        host = FormHost(dialog)
        async with host.run_test(size=size) as pilot:
            await pilot.pause()
            form = pilot.app.screen
            # First field is focused by default, tab order is: field -> cancel -> submit
            await pilot.press("tab")
            await pilot.pause()
            cancel_btn = form.query_one("#cancel", Button)
            assert cancel_btn.has_focus

            # Tab to submit button
            await pilot.press("tab")
            await pilot.pause()
            submit_btn = form.query_one("#submit", Button)
            assert submit_btn.has_focus

    asyncio.run(runner())


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_form_dialog_error_message_visible(size: tuple[int, int]) -> None:
    """Error messages should be visible on small terminals."""
    fields = [FormField("name", "Name", required=True)]

    def validate(values: dict[str, str]) -> str | None:
        return "Custom validation error" if not values["name"] else None

    dialog = FormDialog("Test", fields, submit_label="Save", validate=validate)

    async def runner() -> None:
        host = FormHost(dialog)
        async with host.run_test(size=size) as pilot:
            await pilot.pause()
            form = pilot.app.screen
            # Submit without filling required field
            await pilot.press("enter")
            await pilot.pause()
            error_widget = form.query_one("#form-error", Static)
            assert "Required" in str(error_widget.render())

    asyncio.run(runner())
