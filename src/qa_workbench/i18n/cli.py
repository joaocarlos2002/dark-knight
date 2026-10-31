"""``batman config language ...``: the interface language."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.i18n import (
    ENVIRONMENT_VARIABLE,
    LANGUAGES,
    UnknownLanguageError,
    store_language,
)

language_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="The language of the interface.",
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@language_app.command("list")
def list_command() -> None:
    """List the available languages."""
    for code, name in LANGUAGES:
        typer.echo(f"{code:<6} {name}")


@language_app.command("show")
def show_command() -> None:
    """Show the language in use and where it comes from."""
    try:
        config = AppConfig.load()
    except ConfigurationError as error:
        _fail(str(error))
    names = dict(LANGUAGES)
    typer.echo(f"{config.language}  {names[config.language]}")


@language_app.command("set")
def set_command(
    code: Annotated[str, typer.Argument(help="A language code, such as pt-BR.")],
) -> None:
    """Keep a language for the next runs."""
    try:
        config = AppConfig.load()
        chosen = store_language(config.config_dir, code)
    except (ConfigurationError, UnknownLanguageError, OSError) as error:
        _fail(str(error))
    typer.echo(f"The interface language is now {dict(LANGUAGES)[chosen]} ({chosen}).")
    typer.echo(f"{ENVIRONMENT_VARIABLE}, when set, wins over this choice.")
