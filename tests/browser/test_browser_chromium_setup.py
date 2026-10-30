import subprocess
from pathlib import Path

import pytest

from qa_workbench.browser.chromium import BrowserSetup, SetupStatus
from qa_workbench.browser.errors import BrowserSetupError

READY = SetupStatus(True, Path("chromium.exe"))
MISSING = SetupStatus(True, None, "Chromium is missing.")


def _done(code: int = 0, err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, "", err)


class Probe:
    def __init__(self, *statuses: SetupStatus) -> None:
        self.statuses = list(statuses)

    def __call__(self) -> SetupStatus:
        return self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]


def test_ready_browser_asks_nothing() -> None:
    asked: list[str] = []
    setup = BrowserSetup(Probe(READY), lambda: pytest.fail("must not install"))

    assert setup.ensure(lambda q: asked.append(q) or True).ready
    assert asked == []


def test_missing_browser_is_installed_after_confirmation() -> None:
    installs: list[int] = []
    setup = BrowserSetup(
        Probe(MISSING, MISSING, READY), lambda: installs.append(1) or _done()
    )

    assert setup.ensure(lambda question: "Download" in question).ready
    assert installs == [1]


def test_declining_names_the_command_to_run_later() -> None:
    setup = BrowserSetup(Probe(MISSING), lambda: pytest.fail("must not install"))

    with pytest.raises(BrowserSetupError, match="batman doctor --fix"):
        setup.ensure(lambda question: False)


def test_failed_download_is_explicit_with_context() -> None:
    setup = BrowserSetup(Probe(MISSING), lambda: _done(1, "network unreachable"))

    with pytest.raises(BrowserSetupError, match="network unreachable") as error:
        setup.install()
    assert "exit code 1" in str(error.value)


def test_installer_that_lies_is_caught() -> None:
    setup = BrowserSetup(Probe(MISSING, MISSING), lambda: _done())

    with pytest.raises(BrowserSetupError, match="still not usable"):
        setup.install()


def test_missing_python_package_asks_for_reinstall() -> None:
    gone = SetupStatus(False, None, "Playwright is not importable.")
    setup = BrowserSetup(Probe(gone), lambda: pytest.fail("must not install"))

    with pytest.raises(BrowserSetupError, match="Reinstall"):
        setup.ensure(lambda question: True)
