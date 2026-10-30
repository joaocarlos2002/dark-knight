"""Command-line entry point for Dark Knight QA."""

from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer

from qa_workbench.api.cli import api_app
from qa_workbench.browser.cli import browser_app, doctor_command, preview_channel
from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.core.console import ensure_utf8_output
from qa_workbench.core.logging import configure_logging
from qa_workbench.core.splash import play_startup_splash
from qa_workbench.evidence.cli import evidence_app
from qa_workbench.executions.cli import executions_app
from qa_workbench.integrations.gitlab.cli import gitlab_app
from qa_workbench.plans.cli import plans_app
from qa_workbench.projects.cli import project_app
from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.reports.cli import reports_app
from qa_workbench.requirements.cli import requirements_app
from qa_workbench.review.cli import review_app
from qa_workbench.security.cli import security_app
from qa_workbench.suites.cli import suites_app
from qa_workbench.testcases.cli import cases_app

try:
    __version__ = version("dark-knight-qa")
except PackageNotFoundError:
    __version__ = "0.2.0"

app = typer.Typer(
    add_completion=False,
    help=(
        "Terminal-native, evidence-driven AI quality engineering workbench. "
        "Run it without a command to open the workbench."
    ),
)
app.add_typer(project_app, name="project")
app.add_typer(requirements_app, name="requirements")
app.add_typer(cases_app, name="cases")
app.add_typer(suites_app, name="suites")
app.add_typer(review_app, name="review")
app.add_typer(plans_app, name="plans")
app.add_typer(executions_app, name="executions")
app.add_typer(evidence_app, name="evidence")
app.add_typer(reports_app, name="reports")
app.add_typer(security_app, name="security")
app.add_typer(api_app, name="api")
app.add_typer(browser_app, name="browser")
app.add_typer(gitlab_app, name="gitlab")
app.command("doctor", help="Check that everything the workbench needs is ready.")(
    doctor_command
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"Dark Knight QA {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    context: typer.Context,
    version_option: Annotated[
        bool | None,
        typer.Option(
            "--version",
            help="Show the installed application version and exit.",
            callback=_show_version,
            is_eager=True,
        ),
    ] = None,
    log_level: Annotated[
        str | None,
        typer.Option(
            "--log-level",
            help="Override the configured log level.",
            envvar="DARK_KNIGHT_LOG_LEVEL",
        ),
    ] = None,
    no_splash: Annotated[
        bool,
        typer.Option(
            "--no-splash",
            help="Skip the startup cinematic and open the workbench right away.",
        ),
    ] = False,
) -> None:
    """Open the workbench, or run one of its commands."""
    ensure_utf8_output()
    if version_option:
        return
    try:
        config = AppConfig.load()
    except ConfigurationError as error:
        raise typer.BadParameter(str(error)) from error
    if log_level is not None:
        config = replace(config, log_level=log_level.upper())
    configure_logging(config)
    if context.invoked_subcommand is None:
        _open_workbench(None, config=config, splash=not no_splash)


def _open_workbench(
    project: str | None,
    *,
    config: AppConfig | None = None,
    splash: bool = True,
) -> None:
    """Start the terminal user interface, on a project when one is given."""
    from qa_workbench.tui.app import WorkbenchApp
    from qa_workbench.tui.keymap import Keymap, KeymapError

    try:
        config = config if config is not None else AppConfig.load()
        keymap = Keymap.from_overrides(config.shortcuts)
        opened = (
            ProjectRepository(config.data_dir).open(project)
            if project is not None
            else None
        )
    except (ConfigurationError, KeymapError, ProjectError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    if splash:
        play_startup_splash(config)
    WorkbenchApp(opened, keymap, preview_channel(config)).run()


@app.command()
def tui(
    project: Annotated[
        str | None,
        typer.Option("--project", help="Open the workbench on this project id."),
    ] = None,
    no_splash: Annotated[
        bool,
        typer.Option(
            "--no-splash",
            help="Skip the startup cinematic and open the workbench right away.",
        ),
    ] = False,
) -> None:
    """Open the terminal user interface."""
    _open_workbench(project, splash=not no_splash)


if __name__ == "__main__":
    app()
