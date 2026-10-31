"""``batman api`` commands."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.api.definition import load_definition
from qa_workbench.api.errors import ApiError
from qa_workbench.api.guarded import GuardedTransport
from qa_workbench.api.records import save_flow
from qa_workbench.api.runner import ApiRunner
from qa_workbench.api.transport import HttpTransport, HttpxTransport
from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.workspace import open_repository

api_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Run API tests and keep sanitized results.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]


def default_transport() -> HttpTransport:
    """The real HTTP client. Tests replace this so nothing touches the network."""
    return HttpxTransport()


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@api_app.command("run")
def run_command(
    definition_file: Annotated[Path, typer.Argument(help="YAML test definition.")],
    project: ProjectOption,
    execution: Annotated[
        str | None, typer.Option("--execution", help="Link to an execution.")
    ] = None,
) -> None:
    """Run a definition and save the sanitized result as an API record."""
    try:
        definition = load_definition(definition_file)
        repository = open_repository(project, writable=True)
    except (ApiError, ConfigurationError, ProjectError) as error:
        _fail(str(error))
    try:
        guard = ActionGuard(load_settings(repository.root), AuditLog(repository.root))
    except (SecuritySettingsError, AuditError) as error:
        _fail(str(error))
    flow = ApiRunner(GuardedTransport(default_transport(), guard)).run(definition)
    try:
        record = save_flow(repository, flow, execution=execution)
    except (ApiError, StorageError) as error:
        _fail(str(error))
    for step in flow.steps:
        typer.echo(f"{step.status.upper():<8} {step.name}")
        for check in step.checks:
            if not check.passed:
                typer.echo(f"           {check.name}: {check.detail}")
        if step.error:
            typer.echo(f"           {step.error}")
    typer.echo(f"{flow.status.upper()}: saved as {record.id}")
    if flow.status != "passed":
        raise typer.Exit(1)


@api_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List saved API results."""
    try:
        listing = open_repository(project, writable=False).list_records("API")
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    for record in listing.records:
        typer.echo(
            f"{record.id}  {record.metadata['status']:<7} {record.metadata['title']}"
        )
    for problem in listing.errors:
        typer.echo(f"Damaged record: {problem}", err=True)
    if not listing.records and not listing.errors:
        typer.echo("No API results yet.")


@api_app.command("show")
def show_command(
    record_id: Annotated[str, typer.Argument(help="API record id.")],
    project: ProjectOption,
) -> None:
    """Show a saved API result."""
    try:
        record = open_repository(project, writable=False).get(record_id)
    except (ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    typer.echo(record.body)
