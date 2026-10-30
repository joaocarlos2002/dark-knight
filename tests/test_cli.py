import re

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app
from qa_workbench.tui.app import WorkbenchApp

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_help_exposes_application_usage() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    output = _plain(result.stdout)
    assert "Terminal-native" in output
    assert "--version" in output


def test_version_exposes_application_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Dark Knight QA 0.2.0"


def test_tui_command_starts_the_workbench(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[bool] = []
    monkeypatch.setattr(WorkbenchApp, "run", lambda self: started.append(True))

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 0
    assert started == [True]
