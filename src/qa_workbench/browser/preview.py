"""Browser preview state shared between the agent and the TUI (REQ-022, REQ-023).

The agent and the TUI may live in different processes (``batman browser run`` in
one terminal, the workbench in another), so the preview is a small folder:
``frame.png`` is the latest screenshot and ``state.json`` says what the browser
is doing. Both are replaced atomically, so a reader never sees a half-written
file. Hiding the preview in the TUI only stops reading it; the agent never
knows or waits.
"""

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.ports import BrowserMode
from qa_workbench.storage.atomic import write_text_atomic

STATE_FILE = "state.json"
FRAME_FILE = "frame.png"
CONTROL_FILE = "control.json"


@dataclass(frozen=True)
class PreviewState:
    """What the Browser Preview panel shows."""

    mode: str = BrowserMode.PREVIEW.value
    url: str = ""
    title: str = ""
    action: str = ""
    step: str = ""
    execution_state: str = "idle"
    updated_at: str = ""
    frame_at: str = ""
    screenshot_error: str = ""
    paused: bool = False
    pending_mode: str = ""
    sequence: int = 0


class PreviewChannel:
    """Publishes and reads the preview folder."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @property
    def frame_path(self) -> Path:
        return self.directory / FRAME_FILE

    def publish(self, state: PreviewState, *, frame: Path | None = None) -> None:
        """Write ``state`` and, when given, replace the latest frame."""
        self.directory.mkdir(parents=True, exist_ok=True)
        if frame is not None:
            self._replace_frame(frame)
        write_text_atomic(self.directory / STATE_FILE, json.dumps(asdict(state)))

    def read(self) -> PreviewState | None:
        """The latest state, or ``None`` when no browser ever published one.

        A damaged state file raises :class:`BrowserError` instead of looking
        like an idle browser.
        """
        path = self.directory / STATE_FILE
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PreviewState(**data)
        except (OSError, ValueError, TypeError) as error:
            raise BrowserError(
                f"Browser preview state {path} is unreadable: {error}"
            ) from error

    def request(self, *, mode: str | None = None, paused: bool | None = None) -> None:
        """Ask the running browser to change mode or pause (between actions)."""
        self.directory.mkdir(parents=True, exist_ok=True)
        current = self.read_control()
        if mode is not None:
            current["mode"] = mode
        if paused is not None:
            current["paused"] = paused
        write_text_atomic(self.directory / CONTROL_FILE, json.dumps(current))

    def read_control(self) -> dict[str, object]:
        path = self.directory / CONTROL_FILE
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BrowserError(
                f"Browser control file {path} is unreadable: {error}"
            ) from error
        return data if isinstance(data, dict) else {}

    def latest_frame(self) -> Path | None:
        return self.frame_path if self.frame_path.is_file() else None

    def _replace_frame(self, frame: Path) -> None:
        descriptor, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        os.close(descriptor)
        try:
            Path(temporary).write_bytes(frame.read_bytes())
            os.replace(temporary, self.frame_path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


@dataclass(frozen=True)
class ModeChange:
    """The outcome of asking to change the browser mode."""

    applied: bool
    mode: BrowserMode
    message: str


class PreviewController:
    """Mode and pause controls, safe to call from another thread.

    ``headless`` and ``preview`` differ only in whether frames are captured, so
    they switch at once. ``visible`` needs a browser window, which means
    restarting the browser, so while a run is active the change is only
    recorded for the next run; the controller says so instead of pretending.
    """

    def __init__(self, mode: BrowserMode = BrowserMode.PREVIEW) -> None:
        self._mode = mode
        self._pending: BrowserMode | None = None
        self._running = False
        self._resume = threading.Event()
        self._resume.set()

    @property
    def mode(self) -> BrowserMode:
        return self._mode

    @property
    def pending_mode(self) -> BrowserMode | None:
        return self._pending

    @property
    def paused(self) -> bool:
        return not self._resume.is_set()

    def run_started(self) -> None:
        self._running = True

    def run_finished(self) -> BrowserMode:
        """End the run; returns the mode the next run starts in."""
        self._running = False
        if self._pending is not None:
            self._mode, self._pending = self._pending, None
        return self._mode

    def request_mode(self, mode: BrowserMode) -> ModeChange:
        if mode is self._mode:
            self._pending = None
            return ModeChange(True, mode, f"Already in {mode.value} mode.")
        if not self._running:
            self._mode = mode
            return ModeChange(True, mode, f"Mode set to {mode.value}.")
        if BrowserMode.VISIBLE in (mode, self._mode):
            self._pending = mode
            return ModeChange(
                False,
                mode,
                f"Switching to {mode.value} needs a browser restart; "
                "it will apply to the next run.",
            )
        self._mode = mode
        return ModeChange(True, mode, f"Mode set to {mode.value}.")

    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def wait_if_paused(self, timeout: float | None = None) -> None:
        self._resume.wait(timeout)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
