"""Browser Preview panel: the latest screenshot plus what the browser is doing."""

from typing import Any

from rich.console import Group
from textual.widgets import Static

from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.preview import PreviewChannel, PreviewState
from qa_workbench.browser.render import render_halfblocks
from qa_workbench.tui.components.detail import format_fields

NO_BROWSER_TEXT = "No browser is running. Start one with `batman browser run URL`."


def preview_fields(state: PreviewState) -> list[tuple[str, str]]:
    """The facts shown beside the image."""
    mode = state.mode + (
        f" (next run: {state.pending_mode})" if state.pending_mode else ""
    )
    return [
        ("State", state.execution_state + (" (paused)" if state.paused else "")),
        ("Mode", mode),
        ("URL", state.url),
        ("Title", state.title),
        ("Action", state.action),
        ("Step", state.step),
        ("Updated", state.updated_at),
        ("Screenshot", state.screenshot_error and f"failed: {state.screenshot_error}"),
    ]


class BrowserPreview(Static):
    """Reads the preview folder on a timer, so it never blocks the TUI.

    Hiding the panel only stops redrawing; the browser keeps running and the
    next time the panel is shown it draws the latest frame.
    """

    def __init__(
        self, channel: PreviewChannel, *, refresh_seconds: float = 1.0, **kwargs: Any
    ) -> None:
        super().__init__(NO_BROWSER_TEXT, **kwargs)
        self._channel = channel
        self._refresh_seconds = refresh_seconds
        self._drawn: tuple[int, str, int] | None = None
        self.shown_text = NO_BROWSER_TEXT  # the words on screen, for tests and logs

    def _show(self, content: Any) -> None:
        self.shown_text = content if isinstance(content, str) else ""
        self.update(content)

    def on_mount(self) -> None:
        self.set_interval(self._refresh_seconds, self.refresh_preview)

    def refresh_preview(self, *, force: bool = False) -> None:
        """Redraw when the browser published something new."""
        if not self.display:
            return
        try:
            state = self._channel.read()
        except BrowserError as error:
            self._show(f"Browser preview unavailable: {error}")
            self._drawn = None
            return
        if state is None:
            self._show(NO_BROWSER_TEXT)
            return
        key = (state.sequence, state.frame_at, self.size.width)
        if not force and key == self._drawn:
            return
        self._drawn = key
        details = format_fields(preview_fields(state))
        frame = self._channel.latest_frame()
        if frame is None:
            self._show(f"BROWSER PREVIEW\n\n{details}\n\nNo image captured yet.")
            return
        columns = max(10, self.size.width - 2)
        try:
            image = render_halfblocks(frame, columns, 14)
        except BrowserError as error:
            self._show(f"BROWSER PREVIEW\n\n{details}\n\nImage unavailable: {error}")
            return
        self._show(Group("BROWSER PREVIEW\n", image, "\n" + details))
        self.shown_text = f"BROWSER PREVIEW\n\n{details}"
