import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app
from qa_workbench.tui.app import WorkbenchApp

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[WorkbenchApp]:
    apps: list[WorkbenchApp] = []
    monkeypatch.setattr(WorkbenchApp, "run", lambda self: apps.append(self))
    return apps


def test_running_without_a_command_opens_the_workbench(
    launched: list[WorkbenchApp],
) -> None:
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert len(launched) == 1
    assert launched[0]._project is None


def test_the_tui_command_still_opens_it(launched: list[WorkbenchApp]) -> None:
    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 0
    assert len(launched) == 1


def test_a_command_does_not_open_the_workbench(launched: list[WorkbenchApp]) -> None:
    result = runner.invoke(app, ["project", "list"])

    assert result.exit_code == 0
    assert launched == []


def test_help_and_version_do_not_open_the_workbench(
    launched: list[WorkbenchApp],
) -> None:
    help_result = runner.invoke(app, ["--help"])
    version_result = runner.invoke(app, ["--version"])

    assert help_result.exit_code == 0
    words = re.sub(r"[^A-Za-z]+", " ", help_result.output)
    assert "Run it without a command to open the workbench" in words
    assert version_result.exit_code == 0
    assert version_result.output.startswith("Dark Knight QA ")
    assert launched == []


def test_a_broken_configuration_stops_the_default_launch(
    launched: list[WorkbenchApp], tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[application\n", encoding="utf-8")

    result = runner.invoke(app, [])

    assert result.exit_code != 0
    assert launched == []


def test_conflicting_shortcuts_stop_the_default_launch(
    launched: list[WorkbenchApp], tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[shortcuts]\ntoggle_context = "f1"\n', encoding="utf-8"
    )

    result = runner.invoke(app, [])

    assert result.exit_code == 1
    assert "F1 is assigned to both" in _plain(result.output)
    assert launched == []


def test_the_package_installs_a_batman_command() -> None:
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["scripts"]

    assert scripts["batman"] == "qa_workbench.main:app"
    assert scripts["qa-workbench"] == scripts["batman"]


def test_everything_the_app_imports_is_a_declared_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    declared = {
        re.split(r"[<>=!~ ]", requirement, maxsplit=1)[0].lower()
        for requirement in project["dependencies"]
    }

    assert {"typer", "textual", "pydantic", "pyyaml"} <= declared
    assert "pytest" not in declared and "ruff" not in declared


def test_python_dash_m_runs_the_same_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "qa_workbench", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.startswith("Dark Knight QA ")
