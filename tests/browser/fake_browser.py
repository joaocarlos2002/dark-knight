"""A fake browser for tests: no Playwright, no network, no real browser."""

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.ports import (
    ConsoleEntry,
    LaunchOptions,
    NetworkEntry,
    Observations,
)


@dataclass
class FakeSession:
    options: LaunchOptions
    observations: Observations
    texts: dict[str, str] = field(default_factory=dict)
    visible: set[str] = field(default_factory=set)
    broken_selectors: set[str] = field(default_factory=set)
    fail_screenshots: bool = False
    url: str = "about:blank"
    page_title: str = ""
    calls: list[tuple[str, ...]] = field(default_factory=list)
    screenshots_taken: int = 0
    closed: bool = False

    def _guard(self, selector: str) -> None:
        if selector in self.broken_selectors:
            raise BrowserError(
                "element not found", action="locate", selector=selector, url=self.url
            )

    def navigate(self, url: str, *, timeout_ms: int) -> None:
        self.calls.append(("navigate", url))
        self.url = url
        self.page_title = "Fake page"
        self.observations.console.append(ConsoleEntry("error", "boom", url))
        self.observations.network.append(NetworkEntry("GET", url, 500, "document"))

    def click(self, selector: str, *, timeout_ms: int) -> None:
        self._guard(selector)
        self.calls.append(("click", selector))

    def fill(self, selector: str, value: str, *, timeout_ms: int) -> None:
        self._guard(selector)
        self.calls.append(("fill", selector, value))

    def text_of(self, selector: str, *, timeout_ms: int) -> str:
        self._guard(selector)
        return self.texts.get(selector, "")

    def is_visible(self, selector: str, *, timeout_ms: int) -> bool:
        self._guard(selector)
        return selector in self.visible

    def current_url(self) -> str:
        return self.url

    def title(self) -> str:
        return self.page_title

    def screenshot(self, path: Path) -> None:
        if self.fail_screenshots:
            raise BrowserError("screenshot refused", action="screenshot")
        self.screenshots_taken += 1
        Image.new("RGB", (40, 20), (200, 30, 30)).save(path, format="PNG")

    def save_trace(self, path: Path) -> None:
        path.write_bytes(b"trace")

    def video_path(self) -> Path | None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeDriver:
    def __init__(self, **session_options: object) -> None:
        self.session_options = session_options
        self.sessions: list[FakeSession] = []
        self.launch_error: Exception | None = None

    def launch(self, options: LaunchOptions, observations: Observations) -> FakeSession:
        if self.launch_error is not None:
            raise self.launch_error
        session = FakeSession(options, observations, **self.session_options)  # type: ignore[arg-type]
        self.sessions.append(session)
        return session
