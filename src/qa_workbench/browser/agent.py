"""The Browser Agent: navigation, interaction, assertions, and evidence (REQ-021).

Playwright stays behind the :class:`BrowserDriver` port. The agent adds what the
workbench needs on top: every action is recorded, what the browser reports
(console, network, HTTP failures) is kept, a failed check is an
:class:`AssertionFailed` (a finding) while a browser fault is a
:class:`BrowserError`, and screenshots feed the preview without ever deciding
the test result.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlsplit

from qa_workbench.browser.errors import AssertionFailed, BrowserError
from qa_workbench.browser.ports import (
    BrowserDriver,
    BrowserMode,
    BrowserSession,
    LaunchOptions,
    Observations,
    redact_url,
)
from qa_workbench.browser.preview import (
    PreviewChannel,
    PreviewController,
    PreviewState,
    utc_now,
)
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import Record

DEFAULT_TIMEOUT_MS = 10_000
DEFAULT_REFRESH_SECONDS = 1.0
PAUSE_POLL_SECONDS = 0.2


@dataclass(frozen=True)
class ActionRecord:
    """One thing the browser was asked to do, and how it went."""

    label: str
    ok: bool
    seconds: float
    error: str = ""


@dataclass(frozen=True)
class BrowserArtifacts:
    """Files a run left behind, ready to be registered as evidence."""

    screenshots: tuple[Path, ...] = ()
    trace: Path | None = None
    video: Path | None = None

    def files(self) -> list[tuple[Path, str]]:
        found = [(path, "screenshot") for path in self.screenshots]
        if self.trace is not None:
            found.append((self.trace, "Playwright trace"))
        if self.video is not None:
            found.append((self.video, "video"))
        return found


@dataclass
class BrowserAgent:
    """Drives one browser session and keeps the facts about it."""

    driver: BrowserDriver
    artifacts_dir: Path
    controller: PreviewController = field(default_factory=PreviewController)
    channel: PreviewChannel | None = None
    refresh_seconds: float = DEFAULT_REFRESH_SECONDS
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    video: bool = True
    trace: bool = True
    clock: Callable[[], float] = time.monotonic
    # The guard authorizes every navigation (scope, rate limit, cancellation) and
    # its settings decide which hosts the browser may reach at all. Without a
    # guard only local addresses are allowed.
    guard: ActionGuard | None = None

    def __post_init__(self) -> None:
        self.observations = Observations()
        self.actions: list[ActionRecord] = []
        self.screenshot_failures: list[str] = []
        self._screenshots: list[Path] = []
        self._session: BrowserSession | None = None
        self._artifacts: BrowserArtifacts | None = None
        self._state = PreviewState(mode=self.controller.mode.value)
        self._last_frame = float("-inf")
        self._sequence = 0

    # -- lifecycle -----------------------------------------------------------

    def start(self, *, step: str = "") -> None:
        if self._session is not None:
            raise BrowserError("The browser session is already started.")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts = None
        self.controller.run_started()
        options = LaunchOptions(
            headless=not self.controller.mode.headed,
            artifacts_dir=self.artifacts_dir,
            video=self.video,
            trace=self.trace,
            allow_request=self._host_allowed,
            allowed_hosts=self._resolvable_hosts(),
        )
        try:
            self._session = self.driver.launch(options, self.observations)
        except BaseException:
            self.controller.run_finished()
            raise
        self._publish(execution_state="running", step=step, action="browser started")

    def close(self) -> BrowserArtifacts:
        """Stop the session and return the files it produced."""
        session = self._session
        if session is None:
            # Closing twice (for example after a ``with`` block) is harmless.
            return self._artifacts or BrowserArtifacts(tuple(self._screenshots))
        self._session = None
        trace_path: Path | None = None
        video: Path | None = None
        try:
            if self.trace:
                trace_path = self.artifacts_dir / "trace.zip"
                session.save_trace(trace_path)
            video = session.video_path() if self.video else None
        finally:
            session.close()
            self.controller.run_finished()
            self._publish(execution_state="finished", action="browser closed")
        if video is not None and not video.is_file():
            video = None  # the video file exists only after the context closes
        self._artifacts = BrowserArtifacts(tuple(self._screenshots), trace_path, video)
        return self._artifacts

    def __enter__(self) -> "BrowserAgent":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- actions -------------------------------------------------------------

    def set_step(self, step: str) -> None:
        self._publish(step=step)

    def navigate(self, url: str) -> None:
        """Open ``url`` if it is authorized, and stop if it ends somewhere else."""
        self._require_authorized(url)
        self._run(
            f"navigate {redact_url(url)}",
            lambda s: s.navigate(url, timeout_ms=self.timeout_ms),
        )
        final = self._require_session().current_url()
        if final and not self._host_allowed(final) and not final.startswith("about:"):
            raise BrowserError(
                "The navigation ended at a URL that is not authorized",
                action="navigate",
                url=redact_url(final),
            )

    def click(self, selector: str) -> None:
        self._run(
            f"click {selector}", lambda s: s.click(selector, timeout_ms=self.timeout_ms)
        )

    def fill(self, selector: str, value: str) -> None:
        """Type into a field. The value is never written to the action log."""
        self._run(
            f"fill {selector}",
            lambda s: s.fill(selector, value, timeout_ms=self.timeout_ms),
        )

    def expect_text(self, selector: str, expected: str) -> None:
        """Pass when the element's text contains ``expected``."""
        actual = self._run(
            f"expect text in {selector}",
            lambda s: s.text_of(selector, timeout_ms=self.timeout_ms),
        )
        if expected not in actual:
            raise AssertionFailed(
                f"Text check failed for {selector}", expected=expected, actual=actual
            )

    def expect_visible(self, selector: str) -> None:
        visible = self._run(
            f"expect visible {selector}",
            lambda s: s.is_visible(selector, timeout_ms=self.timeout_ms),
        )
        if not visible:
            raise AssertionFailed(
                f"Element {selector} is not visible",
                expected="visible",
                actual="hidden",
            )

    def screenshot(self, name: str) -> Path | None:
        """Save a screenshot as evidence; ``None`` when it could not be taken.

        A screenshot failure is recorded in :attr:`screenshot_failures` and is
        not, by itself, a functional failure of the test.
        """
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name) or "shot"
        path = self.artifacts_dir / f"{safe}.png"
        session = self._require_session()
        try:
            session.screenshot(path)
        except Exception as error:
            self._record_screenshot_failure(f"{name}: {error}")
            return None
        self._screenshots.append(path)
        self._publish(frame=path, action=f"screenshot {safe}")
        return path

    # -- internals -----------------------------------------------------------

    def _resolvable_hosts(self) -> tuple[str, ...]:
        extra = self.guard.settings.allowed_hosts if self.guard else ()
        return (*LOCAL_HOSTS, *extra)

    def _host_allowed(self, url: str) -> bool:
        if is_local(url):
            return True
        return self.guard is not None and self.guard.settings.host_allowed(url)

    def _require_authorized(self, url: str) -> None:
        if self.guard is None:
            if not is_local(url):
                raise BrowserError(
                    "Only local addresses can be opened without a project scope",
                    action="navigate",
                    url=redact_url(url),
                )
            return
        if not self.guard.settings.host_allowed(url) and not is_local(url):
            raise BrowserError(
                "The host is not in the project's allowed hosts",
                action="navigate",
                url=redact_url(url),
            )
        self.guard.authorize(
            ActionRequest(
                "browser navigation",
                Category.READ,
                f"navigate to {redact_url(url)}",
                # Loopback is always in scope; it is still audited.
                target_url="" if is_local(url) else url,
                requested_by="browser-agent",
            )
        )

    def _require_session(self) -> BrowserSession:
        if self._session is None:
            raise BrowserError("The browser session is not started.")
        return self._session

    def _run[T](self, label: str, operation: Callable[[BrowserSession], T]) -> T:
        session = self._require_session()
        self._honor_controls()
        self._publish(action=label)
        started = self.clock()
        try:
            result = operation(session)
        except BrowserError as error:
            elapsed = self.clock() - started
            self.actions.append(ActionRecord(label, False, elapsed, str(error)))
            self._publish(action=f"failed: {label}")
            raise
        self.actions.append(ActionRecord(label, True, self.clock() - started))
        self._capture_frame()
        return result

    def _honor_controls(self) -> None:
        """Apply mode/pause requests from the TUI, waiting while paused."""
        self._poll_control()
        if self.controller.paused:
            self._publish(action="paused")
            while self.controller.paused:
                self.controller.wait_if_paused(PAUSE_POLL_SECONDS)
                self._poll_control()
            self._publish(action="resumed")

    def _poll_control(self) -> None:
        if self.channel is None:
            return
        control = self.channel.read_control()
        wanted = control.get("mode")
        if isinstance(wanted, str) and wanted and wanted != self.controller.mode.value:
            try:
                self.controller.request_mode(BrowserMode(wanted))
            except ValueError:
                pass  # an unknown mode in the file is ignored, not applied
        paused = control.get("paused")
        if paused is True and not self.controller.paused:
            self.controller.pause()
        elif paused is False and self.controller.paused:
            self.controller.resume()

    def _capture_frame(self) -> None:
        if self.controller.mode is not BrowserMode.PREVIEW or self.channel is None:
            return
        now = self.clock()
        if now - self._last_frame < self.refresh_seconds:
            return
        self._last_frame = now
        frame = self.artifacts_dir / ".preview-frame.png"
        try:
            self._require_session().screenshot(frame)
        except Exception as error:
            self._record_screenshot_failure(f"preview frame: {error}")
            return
        self._publish(frame=frame)

    def _record_screenshot_failure(self, message: str) -> None:
        self.screenshot_failures.append(message)
        self._publish(screenshot_error=message)

    def _publish(self, frame: Path | None = None, **changes: object) -> None:
        session = self._session
        page: dict[str, object] = {}
        if session is not None:
            try:
                page = {
                    "url": redact_url(session.current_url()),
                    "title": session.title(),
                }
            except Exception:  # the page may be closing; keep the last known
                page = {}
        pending = self.controller.pending_mode
        self._sequence += 1
        values: dict[str, object] = {
            "mode": self.controller.mode.value,
            "paused": self.controller.paused,
            "pending_mode": pending.value if pending else "",
            "updated_at": utc_now(),
            "sequence": self._sequence,
            **page,
            **changes,
        }
        if frame is not None:
            values.update(frame_at=utc_now(), screenshot_error="")
        self._state = replace(self._state, **values)  # type: ignore[arg-type]
        if self.channel is not None:
            self.channel.publish(self._state, frame=frame)


LOCAL_HOSTS = ("localhost", "127.0.0.1")


def is_local(url: str) -> bool:
    """A loopback address or a local file: always reachable, never external."""
    parts = urlsplit(url)
    if parts.scheme == "file":
        return True
    return parts.scheme in ("http", "https") and (parts.hostname or "").lower() in (
        "localhost",
        "127.0.0.1",
        "::1",
    )


def register_artifacts(
    store: EvidenceStore,
    artifacts: BrowserArtifacts,
    *,
    execution: str | None = None,
    step: str | None = None,
    source_url: str | None = None,
) -> list[Record]:
    """Register what a run produced as immutable, hashed evidence."""
    return [
        store.register(
            path,
            source="playwright",
            description=f"{kind} captured by the Browser Agent",
            step=step,
            execution=execution,
            source_url=source_url,
        )
        for path, kind in artifacts.files()
    ]
