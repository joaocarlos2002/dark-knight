import re
from pathlib import Path

import pytest
from fake_browser import FakeDriver
from typer.testing import CliRunner

from qa_workbench.browser import cli
from qa_workbench.browser.chromium import BrowserSetup, SetupStatus
from qa_workbench.main import app

runner = CliRunner()
READY = SetupStatus(True, Path("chromium.exe"))


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> FakeDriver:
    fake = FakeDriver(texts={"body": "Welcome"})
    monkeypatch.setattr(cli, "default_driver", lambda: fake)
    monkeypatch.setattr(cli, "default_setup", lambda: BrowserSetup(lambda: READY))
    return fake


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


def test_run_opens_the_page_and_reports_what_the_browser_saw(
    driver: FakeDriver, isolated: Path
) -> None:
    result, out = _run(
        "browser", "run", "http://localhost", "--expect-text", "Welcome",
        "--out", str(isolated / "out"),
    )  # fmt: skip

    assert result.exit_code == 0, out
    assert "Console errors: 1" in out and "HTTP failures: 1" in out
    assert "Saved screenshot" in out
    assert "Saved console log" in out and "Saved network log" in out
    assert (isolated / "out" / "page.png").is_file()


def test_failed_check_exits_with_an_error(driver: FakeDriver, isolated: Path) -> None:
    result, out = _run(
        "browser", "run", "http://localhost", "--expect-text", "Goodbye",
        "--out", str(isolated / "out"),
    )  # fmt: skip

    assert result.exit_code == 1
    assert "Check failed" in out


def test_unknown_mode_is_rejected(driver: FakeDriver) -> None:
    result, out = _run("browser", "run", "http://localhost", "--mode", "sideways")

    assert result.exit_code == 1 and "Unknown mode" in out


def test_launch_failure_is_reported_not_swallowed(
    driver: FakeDriver, isolated: Path
) -> None:
    from qa_workbench.browser.errors import BrowserError

    driver.launch_error = BrowserError("no chromium")
    result, out = _run(
        "browser", "run", "http://localhost", "--out", str(isolated / "out")
    )

    assert result.exit_code == 1 and "no chromium" in out


def test_run_registers_evidence_in_a_project(
    driver: FakeDriver, isolated: Path
) -> None:
    assert _run("project", "create", "Demo")[0].exit_code == 0

    result, out = _run(
        "browser", "run", "http://localhost", "-p", "PROJ-001",
        "--out", str(isolated / "out"),
    )  # fmt: skip

    assert result.exit_code == 0, out
    assert "Registered EVD-001" in out


def test_execution_without_project_is_refused(driver: FakeDriver) -> None:
    result, out = _run("browser", "run", "http://localhost", "--execution", "EXEC-001")

    assert result.exit_code == 1 and "--project" in out


def test_missing_browser_without_consent_points_to_doctor(
    monkeypatch: pytest.MonkeyPatch, driver: FakeDriver
) -> None:
    missing = SetupStatus(True, None, "Chromium is missing.")
    monkeypatch.setattr(
        cli, "default_setup", lambda: BrowserSetup(lambda: missing, lambda: 1 / 0)
    )

    result, out = _run("browser", "run", "http://localhost")

    assert result.exit_code == 1 and "batman doctor --fix" in out


def test_doctor_reports_ready_and_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "default_setup", lambda: BrowserSetup(lambda: READY))
    assert "ready" in _run("doctor")[1]

    missing = SetupStatus(True, None, "Chromium is missing.")
    monkeypatch.setattr(cli, "default_setup", lambda: BrowserSetup(lambda: missing))
    result, out = _run("doctor")
    assert result.exit_code == 1 and "doctor --fix" in out


def test_doctor_fix_installs_with_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    states = [SetupStatus(True, None, "missing"), SetupStatus(True, None, "missing")]

    def probe() -> SetupStatus:
        return states.pop(0) if states else READY

    monkeypatch.setattr(
        cli,
        "default_setup",
        lambda: BrowserSetup(probe, lambda: subprocess.CompletedProcess([], 0, "", "")),
    )

    result, out = _run("doctor", "--fix", "--yes")

    assert result.exit_code == 0 and "installed" in out


def test_control_writes_requests_the_agent_reads(isolated: Path) -> None:
    result, out = _run("browser", "control", "--mode", "headless", "--pause")
    assert result.exit_code == 0, out

    state = _run("browser", "status")[1]
    assert "No browser has published" in state
    assert _run("browser", "control")[0].exit_code == 1
    assert _run("browser", "control", "--pause", "--resume")[0].exit_code == 1
    assert _run("browser", "control", "--mode", "x")[0].exit_code == 1
