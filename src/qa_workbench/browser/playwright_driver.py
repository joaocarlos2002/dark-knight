"""The Playwright adapter for the Browser Agent (the only place it is imported)."""

from pathlib import Path
from typing import Any

from qa_workbench.browser.errors import BrowserError, BrowserSetupError, BrowserTimeout
from qa_workbench.browser.ports import (
    ConsoleEntry,
    LaunchOptions,
    NetworkEntry,
    Observations,
    redact_url,
)

_CONSOLE_LEVELS = {"error": "error", "warning": "warning"}


class PlaywrightDriver:
    """Launches Chromium through Playwright's synchronous API.

    Playwright's sync API belongs to one thread, so a run (and its preview
    captures) must stay on the thread that called :meth:`launch`.
    """

    def launch(
        self, options: LaunchOptions, observations: Observations
    ) -> "PlaywrightSession":
        try:
            from playwright.sync_api import Error, sync_playwright
        except ImportError as error:
            raise BrowserSetupError(
                "Playwright is not installed in this environment."
            ) from error
        playwright = sync_playwright().start()
        try:
            browser = playwright.chromium.launch(headless=options.headless)
        except Error as error:
            playwright.stop()
            raise BrowserSetupError(
                "Chromium could not be started. Run `batman doctor --fix` to "
                f"install the browsers. Details: {_first_line(error)}"
            ) from error
        context_options: dict[str, Any] = {}
        if options.video:
            context_options["record_video_dir"] = str(options.artifacts_dir / "video")
        context = browser.new_context(**context_options)
        if options.trace:
            context.tracing.start(screenshots=True, snapshots=True)
        page = context.new_page()
        _observe(page, observations)
        return PlaywrightSession(playwright, browser, context, page, options)


def _first_line(error: BaseException) -> str:
    return (str(error).strip().splitlines() or [type(error).__name__])[0]


def _observe(page: Any, observations: Observations) -> None:
    def on_console(message: Any) -> None:
        level = _CONSOLE_LEVELS.get(message.type, message.type)
        location = message.location or {}
        observations.console.append(
            ConsoleEntry(level, message.text, str(location.get("url", "")))
        )

    def on_response(response: Any) -> None:
        request = response.request
        observations.network.append(
            NetworkEntry(
                request.method,
                redact_url(response.url),
                response.status,
                request.resource_type,
            )
        )

    def on_request_failed(request: Any) -> None:
        observations.network.append(
            NetworkEntry(
                request.method,
                redact_url(request.url),
                None,
                request.resource_type,
                failure=request.failure or "request failed",
            )
        )

    page.on("console", on_console)
    page.on("pageerror", lambda error: observations.page_errors.append(str(error)))
    page.on("response", on_response)
    page.on("requestfailed", on_request_failed)


class PlaywrightSession:
    """One Chromium context with a single page."""

    def __init__(
        self, playwright: Any, browser: Any, context: Any, page: Any, options: Any
    ) -> None:
        self._playwright = playwright
        self._browser = browser
        self._context = context
        self._page = page
        self._options = options

    def _call(self, action: str, selector: str | None, operation: Any) -> Any:
        from playwright.sync_api import Error, TimeoutError

        try:
            return operation()
        except TimeoutError as error:
            raise BrowserTimeout(
                f"Timed out: {_first_line(error)}",
                action=action,
                selector=selector,
                url=self._page.url,
            ) from error
        except Error as error:
            raise BrowserError(
                _first_line(error), action=action, selector=selector, url=self._page.url
            ) from error

    def navigate(self, url: str, *, timeout_ms: int) -> None:
        self._call("navigate", None, lambda: self._page.goto(url, timeout=timeout_ms))

    def click(self, selector: str, *, timeout_ms: int) -> None:
        self._call(
            "click",
            selector,
            lambda: self._page.click(selector, timeout=timeout_ms),
        )

    def fill(self, selector: str, value: str, *, timeout_ms: int) -> None:
        self._call(
            "fill",
            selector,
            lambda: self._page.fill(selector, value, timeout=timeout_ms),
        )

    def text_of(self, selector: str, *, timeout_ms: int) -> str:
        return self._call(
            "read text",
            selector,
            lambda: self._page.inner_text(selector, timeout=timeout_ms),
        )

    def is_visible(self, selector: str, *, timeout_ms: int) -> bool:
        return self._call(
            "check visibility",
            selector,
            lambda: self._page.locator(selector).first.is_visible(timeout=timeout_ms),
        )

    def current_url(self) -> str:
        return self._page.url

    def title(self) -> str:
        return self._page.title()

    def screenshot(self, path: Path) -> None:
        self._call("screenshot", None, lambda: self._page.screenshot(path=str(path)))

    def save_trace(self, path: Path) -> None:
        self._call(
            "save trace", None, lambda: self._context.tracing.stop(path=str(path))
        )

    def video_path(self) -> Path | None:
        video = self._page.video
        if video is None:
            return None
        try:
            return Path(video.path())
        except Exception:
            return None

    def close(self) -> None:
        try:
            self._context.close()  # finalizes the video file
            self._browser.close()
        finally:
            self._playwright.stop()
