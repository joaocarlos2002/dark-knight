"""What the Browser Agent needs from a browser, independent of Playwright."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SENSITIVE_QUERY = ("token", "key", "secret", "password", "passwd", "auth", "session")


class BrowserMode(StrEnum):
    """How the browser is shown: ``preview`` is the recommended default."""

    HEADLESS = "headless"
    PREVIEW = "preview"
    VISIBLE = "visible"

    @property
    def headed(self) -> bool:
        return self is BrowserMode.VISIBLE


@dataclass(frozen=True)
class LaunchOptions:
    """How to start a browser session."""

    headless: bool
    artifacts_dir: Path
    video: bool = True
    trace: bool = True


@dataclass(frozen=True)
class ConsoleEntry:
    level: str
    text: str
    location: str = ""


@dataclass(frozen=True)
class NetworkEntry:
    """One request. Headers and bodies are never kept, so no credential is."""

    method: str
    url: str
    status: int | None
    resource_type: str = ""
    failure: str | None = None

    @property
    def failed(self) -> bool:
        return self.failure is not None or (self.status or 0) >= 400


def redact_url(url: str) -> str:
    """Hide the value of query parameters that look like credentials."""
    parts = urlsplit(url)
    if not parts.query:
        return url
    pairs = [
        (name, "[redacted]" if any(s in name.lower() for s in _SENSITIVE_QUERY) else v)
        for name, v in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(pairs, safe="[]")))


@dataclass
class Observations:
    """What the browser reported while the test ran."""

    console: list[ConsoleEntry] = field(default_factory=list)
    network: list[NetworkEntry] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)

    @property
    def console_errors(self) -> list[ConsoleEntry]:
        return [entry for entry in self.console if entry.level == "error"]

    @property
    def http_failures(self) -> list[NetworkEntry]:
        return [entry for entry in self.network if entry.failed]


class BrowserSession(Protocol):
    """One open browser context with a single page."""

    def navigate(self, url: str, *, timeout_ms: int) -> None: ...
    def click(self, selector: str, *, timeout_ms: int) -> None: ...
    def fill(self, selector: str, value: str, *, timeout_ms: int) -> None: ...
    def text_of(self, selector: str, *, timeout_ms: int) -> str: ...
    def is_visible(self, selector: str, *, timeout_ms: int) -> bool: ...
    def current_url(self) -> str: ...
    def title(self) -> str: ...
    def screenshot(self, path: Path) -> None: ...
    def save_trace(self, path: Path) -> None: ...
    def video_path(self) -> Path | None: ...
    def close(self) -> None: ...


class BrowserDriver(Protocol):
    """Starts sessions. The Playwright adapter is the only real implementation."""

    def launch(
        self, options: LaunchOptions, observations: Observations
    ) -> BrowserSession: ...
