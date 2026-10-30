"""Command-line entry point for Dark Knight QA."""

from importlib.metadata import PackageNotFoundError, version
from typing import Annotated

import typer

try:
    __version__ = version("dark-knight-qa")
except PackageNotFoundError:
    __version__ = "0.1.0"

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
) -> None:
    """Run the Dark Knight QA workbench."""


if __name__ == "__main__":
    app()
