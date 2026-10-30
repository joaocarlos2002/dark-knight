"""Command-line entry point for Dark Knight QA."""

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.core.logging import configure_logging

try:
    __version__ = version("dark-knight-qa")
except PackageNotFoundError:
    __version__ = "0.2.0"

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Terminal-native, evidence-driven AI quality engineering workbench.",
)


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


if __name__ == "__main__":
    app()
