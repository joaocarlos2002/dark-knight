"""Confirmation dialog for sensitive actions."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmationDialog(ModalScreen[bool]):
    """Asks the user to confirm an action. Dismisses with ``True`` or ``False``.

    Cancelling is always the safe outcome: Escape cancels, and a destructive
    dialog starts with Cancel focused so a stray Enter does nothing harmful.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        message: str,
        *,
        confirm_label: str = "Confirm",
        destructive: bool = False,
    ) -> None:
        if not title.strip() or not message.strip():
            raise ValueError("ConfirmationDialog needs a title and a message.")
        super().__init__()
        self._title = title.strip()
        self._message = message.strip()
        self._confirm_label = confirm_label
        self._destructive = destructive

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="dialog-title")
            yield Static(self._message, id="dialog-message")
            with Horizontal():
                yield Button(
                    self._confirm_label,
                    id="confirm",
                    variant="error" if self._destructive else "primary",
                )
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#cancel" if self._destructive else "#confirm").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        self.dismiss(event.button.id == "confirm")

    def action_cancel(self) -> None:
        self.dismiss(False)
