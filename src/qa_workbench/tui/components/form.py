"""Form dialog: a few labelled inputs, validated before it closes."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


@dataclass(frozen=True)
class FormField:
    key: str
    label: str
    placeholder: str = ""
    required: bool = False
    default: str = ""  # typed in already; a placeholder is only a hint


Validator = Callable[[dict[str, str]], str | None]


class FormDialog(ModalScreen["dict[str, str] | None"]):
    """Collects text fields. Dismisses with the values, or ``None`` if cancelled.

    A required field left empty, or an error returned by ``validate``, is shown
    inside the dialog and the dialog stays open, so nothing typed is lost.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        fields: Sequence[FormField],
        *,
        submit_label: str = "Save",
        validate: Validator | None = None,
        commit: Validator | None = None,
    ) -> None:
        if not title.strip() or not fields:
            raise ValueError("FormDialog needs a title and at least one field.")
        keys = [f.key for f in fields]
        if len(set(keys)) != len(keys):
            raise ValueError("FormDialog field keys must be unique.")
        super().__init__()
        self._title = title.strip()
        self._fields = tuple(fields)
        self._submit_label = submit_label
        self._validate = validate
        # Does the work on submit. A returned message keeps the dialog open with
        # what was typed; ``None`` means it worked and the dialog closes.
        self._commit = commit

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="dialog-title")
            for field in self._fields:
                suffix = " *" if field.required else ""
                yield Static(f"{field.label}{suffix}", classes="form-label")
                yield Input(
                    value=field.default,
                    placeholder=field.placeholder,
                    id=f"field-{field.key}",
                )
            yield Static("", id="form-error")
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button(self._submit_label, id="submit", variant="primary")

    def on_mount(self) -> None:
        self.query_one(f"#field-{self._fields[0].key}", Input).focus()

    def values(self) -> dict[str, str]:
        return {
            f.key: self.query_one(f"#field-{f.key}", Input).value.strip()
            for f in self._fields
        }

    def error_for(self, values: dict[str, str]) -> str | None:
        missing = [f.label for f in self._fields if f.required and not values[f.key]]
        if missing:
            return f"Required: {', '.join(missing)}."
        return self._validate(values) if self._validate else None

    def _submit(self) -> None:
        values = self.values()
        error = self.error_for(values)
        if not error and self._commit is not None:
            error = self._commit(values)
        if error:
            self.query_one("#form-error", Static).update(error)
            return
        self.dismiss(values)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "submit":
            self._submit()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
