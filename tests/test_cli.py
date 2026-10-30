from typer.testing import CliRunner

from qa_workbench.main import app


runner = CliRunner()


def test_help_exposes_application_usage() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Terminal-native" in result.stdout
    assert "--version" in result.stdout


def test_version_exposes_application_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "Dark Knight QA 0.1.0"
