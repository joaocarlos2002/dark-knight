import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Static

from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.theme import SHELL_CSS


class Host(App[None]):
    CSS = SHELL_CSS

    def __init__(self, dialog: ConfirmationDialog) -> None:
        super().__init__()
        self._dialog = dialog
        self.result: bool | None = None

    def compose(self) -> ComposeResult:
        yield Static("host")

    def on_mount(self) -> None:
        self.push_screen(self._dialog, self._record)

    def _record(self, result: bool | None) -> None:
        self.result = result


def _run(dialog: ConfirmationDialog, keys: list[str]) -> Host:
    host = Host(dialog)

    async def runner() -> None:
        async with host.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press(*keys)
            await pilot.pause()

    asyncio.run(runner())
    return host


def _dialog(**kwargs: object) -> ConfirmationDialog:
    return ConfirmationDialog("Archive project", "PROJ-001 will be hidden.", **kwargs)  # type: ignore[arg-type]


def test_enter_confirms_a_normal_dialog() -> None:
    assert _run(_dialog(), ["enter"]).result is True


def test_escape_cancels() -> None:
    assert _run(_dialog(), ["escape"]).result is False


def test_destructive_dialog_starts_on_cancel() -> None:
    assert _run(_dialog(destructive=True), ["enter"]).result is False


def test_destructive_dialog_can_still_be_confirmed_deliberately() -> None:
    host = _run(
        _dialog(destructive=True, confirm_label="Archive"), ["shift+tab", "enter"]
    )

    assert host.result is True


def test_dialog_shows_title_message_and_custom_label() -> None:
    host = Host(_dialog(confirm_label="Archive"))

    async def runner() -> None:
        async with host.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            screen = host.screen
            assert str(screen.query_one("#dialog-title", Static).render()) == (
                "Archive project"
            )
            assert "PROJ-001" in str(
                screen.query_one("#dialog-message", Static).render()
            )
            assert str(screen.query_one("#confirm", Button).label) == "Archive"

    asyncio.run(runner())


@pytest.mark.parametrize(("title", "message"), [("", "x"), ("x", " ")])
def test_dialog_requires_title_and_message(title: str, message: str) -> None:
    with pytest.raises(ValueError, match="needs a title and a message"):
        ConfirmationDialog(title, message)
