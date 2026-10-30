import re

from typer.testing import CliRunner

from qa_workbench.main import app

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
