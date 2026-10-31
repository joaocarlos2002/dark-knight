"""Choice dialog: pick one item from a list (a model, for example)."""

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static


class ChoiceDialog(ModalScreen["str | None"]):
    """Dismisses with the chosen item, or ``None`` if cancelled (Escape)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self, title: str, choices: Sequence[str], *, current: str = "", note: str = ""
    ) -> None:
        if not title.strip() or not choices:
            raise ValueError("ChoiceDialog needs a title and at least one choice.")
        super().__init__()
        self._title = title.strip()
        self._choices = tuple(choices)
        self._current = current
        self._note = note.strip()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="dialog-title")
            if self._note:
                yield Static(self._note, id="dialog-message")
            yield OptionList(*self._choices, id="choices")

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        if self._current in self._choices:
            options.highlighted = self._choices.index(self._current)
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(self._choices[event.option_index])

    def action_cancel(self) -> None:
        self.dismiss(None)
