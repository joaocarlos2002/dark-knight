"""``batman config token ...``: keep API tokens in the application."""

import sys
from typing import Annotated, NoReturn

import typer

from qa_workbench.security.credentials import (
    SERVICES,
    CredentialError,
    CredentialStore,
    StoredEnvironment,
    default_store,
    variable_for,
)

config_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Application configuration.",
)
token_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Keep API tokens in the application instead of exporting them each time.",
)
config_app.add_typer(token_app, name="token")

NameArgument = Annotated[
    str,
    typer.Argument(help=f"A service ({', '.join(SERVICES)}) or a variable name."),
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _store() -> CredentialStore:
    store = default_store()
    if store is None:
        _fail("The configuration is invalid, so there is nowhere to keep tokens.")
    return store


@token_app.command("set")
def set_command(
    name: NameArgument,
    stdin: Annotated[
        bool,
        typer.Option("--stdin", help="Read the token from standard input."),
    ] = False,
) -> None:
    """Store a token. It is asked for without echo, so it stays out of your
    shell history. An environment variable of the same name still wins."""
    try:
        variable = variable_for(name)
        value = (
            sys.stdin.readline()
            if stdin
            else typer.prompt(f"Token for {variable}", hide_input=True)
        )
        _store().set(name, value)
    except CredentialError as error:
        _fail(str(error))
    typer.echo(f"Stored {variable}. The value is not shown again.")


@token_app.command("show")
def show_command() -> None:
    """Show which tokens are set and where they come from, never their values."""
    store = _store()
    try:
        environment = StoredEnvironment(store)
        names = list(dict.fromkeys([*SERVICES.values(), *store.names()]))
        for variable in names:
            source = environment.source_of(variable)
            state = f"set ({source})" if source else "not set"
            typer.echo(f"{variable:<24} {state}")
    except CredentialError as error:
        _fail(str(error))


@token_app.command("remove")
def remove_command(name: NameArgument) -> None:
    """Remove a stored token. An environment variable is not touched."""
    try:
        variable = variable_for(name)
        removed = _store().remove(name)
    except CredentialError as error:
        _fail(str(error))
    typer.echo(f"Removed {variable}." if removed else f"{variable} was not stored.")
