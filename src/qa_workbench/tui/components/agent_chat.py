"""Agent chat: a transcript and a message box."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Input, Static

YOU, ASSISTANT, NOTICE = "YOU", "ALFRED", "NOTICE"


class AgentChat(Vertical):
    """Shows who said what and posts :class:`Submitted` when the user sends text.

    Speaker names are written out (never only a color), and while the agent is
    working the box is disabled so a second question cannot overlap the first.
    """

    class Submitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, assistant_name: str = ASSISTANT, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._assistant = assistant_name
        self.lines: list[tuple[str, str]] = []  # (speaker, text), for tests and logs

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="chat-scroll"):
            yield Static("", id="chat-log", markup=False)
        yield Input(
            placeholder="Ask (Enter sends; @REQ-001 attaches a record)", id="chat-input"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self.post_message(self.Submitted(text))

    # -- transcript --------------------------------------------------------------

    def add(self, speaker: str, text: str) -> None:
        self.lines.append((speaker, text))
        self._redraw()

    def add_user(self, text: str) -> None:
        self.add(YOU, text)

    def add_assistant(self, text: str) -> None:
        self.add(self._assistant, text)

    def add_notice(self, text: str) -> None:
        self.add(NOTICE, text)

    def clear(self) -> None:
        self.lines.clear()
        self._redraw()

    def set_busy(self, busy: bool) -> None:
        box = self.query_one("#chat-input", Input)
        box.disabled = busy
        box.placeholder = (
            "Working..." if busy else "Ask (Enter sends; @REQ-001 attaches a record)"
        )
        if not busy:
            box.focus()

    def focus_input(self) -> None:
        self.query_one("#chat-input", Input).focus()

    def transcript(self) -> str:
        blocks = []
        for speaker, text in self.lines:
            body = "\n".join(f"  {line}" for line in text.splitlines() or [""])
            blocks.append(f"{speaker}\n{body}")
        return "\n\n".join(blocks)

    def _redraw(self) -> None:
        if not self.is_mounted:
            return
        self.query_one("#chat-log", Static).update(self.transcript())
        self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=False)
