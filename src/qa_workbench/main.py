"""Command-line entry point for Dark Knight QA."""

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.core.logging import configure_logging
from qa_workbench.plans.cli import plans_app
from qa_workbench.projects.cli import project_app
from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.requirements.cli import requirements_app
from qa_workbench.review.cli import review_app
from qa_workbench.testcases.cli import cases_app

try:
    __version__ = version("dark-knight-qa")
except PackageNotFoundError:
    __version__ = "0.2.0"

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Terminal-native, evidence-driven AI quality engineering workbench.",
)
app.add_typer(project_app, name="project")
app.add_typer(requirements_app, name="requirements")
app.add_typer(cases_app, name="cases")
app.add_typer(review_app, name="review")
app.add_typer(plans_app, name="plans")


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"Dark Knight QA {__version__}")
        raise typer.Exit()


@app.callback()
def main(
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
) -> None:
    """Run the Dark Knight QA workbench."""
    if version_option:
        return
    try:
        config = AppConfig.load()
    except ConfigurationError as error:
        raise typer.BadParameter(str(error)) from error
    if log_level is not None:
        config = AppConfig(
            config_dir=config.config_dir,
            data_dir=config.data_dir,
            log_level=log_level.upper(),
            log_file=config.log_file,
        )
    configure_logging(config)


@app.command()
def tui(
    project: Annotated[
        str | None,
        typer.Option("--project", help="Open the workbench on this project id."),
    ] = None,
) -> None:
    """Open the terminal user interface."""
    from qa_workbench.tui.app import WorkbenchApp
    from qa_workbench.tui.keymap import Keymap, KeymapError

    try:
        config = AppConfig.load()
        keymap = Keymap.from_overrides(config.shortcuts)
        opened = (
            ProjectRepository(config.data_dir).open(project)
            if project is not None
            else None
        )
    except (ConfigurationError, KeymapError, ProjectError) as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(1) from error
    WorkbenchApp(opened, keymap).run()


if __name__ == "__main__":
    app()
