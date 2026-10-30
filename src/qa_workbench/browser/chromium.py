"""Guided setup of the browsers Playwright drives.

The Python package ships with the workbench, but Chromium is a separate
download. This module checks whether it is there, and installs it only after
the person agrees (or passed ``--yes``). Nothing is downloaded silently, and a
failed download is an explicit error with the command to retry.
"""

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from qa_workbench.browser.errors import BrowserSetupError

INSTALL_HINT = "batman doctor --fix"


@dataclass(frozen=True)
class SetupStatus:
    """Whether the browser is ready, and why not."""

    playwright_installed: bool
    chromium_path: Path | None
    detail: str = ""

    @property
    def ready(self) -> bool:
        return self.playwright_installed and self.chromium_path is not None


def probe_chromium() -> SetupStatus:
    """Look for the Playwright package and its Chromium build."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        return SetupStatus(False, None, f"Playwright is not importable: {error}")
    try:
        with sync_playwright() as playwright:
            path = Path(playwright.chromium.executable_path)
    except Exception as error:
        return SetupStatus(True, None, f"Playwright could not be queried: {error}")
    if not path.exists():
        return SetupStatus(True, None, f"Chromium is missing (expected at {path}).")
    return SetupStatus(True, path)


def install_chromium() -> subprocess.CompletedProcess[str]:
    """Download Chromium with Playwright's own installer."""
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        check=False,
    )


class BrowserSetup:
    """Checks and installs the browser, with the two steps replaceable in tests."""

    def __init__(
        self,
        probe: Callable[[], SetupStatus] = probe_chromium,
        installer: Callable[[], subprocess.CompletedProcess[str]] = install_chromium,
    ) -> None:
        self._probe = probe
        self._installer = installer

    def status(self) -> SetupStatus:
        return self._probe()

    def install(self) -> SetupStatus:
        """Install Chromium and verify it; raises if it is still not usable."""
        status = self._probe()
        if not status.playwright_installed:
            raise BrowserSetupError(f"{status.detail} Reinstall the application.")
        result = self._installer()
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
            raise BrowserSetupError(
                f"Installing Chromium failed (exit code {result.returncode}): "
                f"{' | '.join(tail) or 'no output'}. Check your connection and "
                f"retry with `{INSTALL_HINT}`."
            )
        after = self._probe()
        if not after.ready:
            raise BrowserSetupError(
                f"The installer finished but Chromium is still not usable: "
                f"{after.detail} Retry with `{INSTALL_HINT}`."
            )
        return after

    def ensure(self, confirm: Callable[[str], bool]) -> SetupStatus:
        """Return a ready status, offering to install Chromium when it is missing.

        ``confirm`` is asked once with an explanation. Declining raises
        :class:`BrowserSetupError` naming the command to run later.
        """
        status = self._probe()
        if status.ready:
            return status
        if not status.playwright_installed:
            raise BrowserSetupError(f"{status.detail} Reinstall the application.")
        question = (
            "The browser used for web tests (Chromium, roughly 150 MB) is not "
            "installed yet. Download it now?"
        )
        if not confirm(question):
            raise BrowserSetupError(
                f"Chromium is not installed. Run `{INSTALL_HINT}` when you are ready."
            )
        return self.install()
