"""``qa-workbench executions`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.executions.schema import EXECUTION_TYPES
from qa_workbench.executions.service import ExecutionError, create_execution, move
from qa_workbench.executions.states import (
    RESULT_STATES,
    InvalidTransition,
    State,
    next_states,
)
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.workspace import open_repository

executions_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Run test cases through a validated lifecycle.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]
ExecutionArgument = Annotated[
    str, typer.Argument(help="Execution id, such as EXEC-001.")
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _open(project: str, *, writable: bool) -> MarkdownRepository:
    try:
        return open_repository(project, writable=writable)
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))


@executions_app.command("states")
def states_command() -> None:
    """Show the lifecycle: every state and where it can go next."""
    for state in State:
        targets = ", ".join(sorted(s.value for s in next_states(state))) or "(final)"
        marker = " [result]" if state in RESULT_STATES else ""
        typer.echo(f"{state.value:<18}{marker:<9} -> {targets}")


@executions_app.command("create")
def create_command(
    project: ProjectOption,
    execution_type: Annotated[
        str,
        typer.Option(
            "--type",
            help=f"One of: {', '.join(sorted(EXECUTION_TYPES))}.",
        ),
    ],
    executor: Annotated[str, typer.Option(help="Who or what runs it.")],
    environment: Annotated[str, typer.Option(help="Environment, e.g. staging.")],
    case: Annotated[
        str | None, typer.Option(help="TC id (not needed for exploratory).")
    ] = None,
    plan: Annotated[str | None, typer.Option(help="TP id.")] = None,
    suite: Annotated[str | None, typer.Option(help="SUITE id.")] = None,
    version: Annotated[str | None, typer.Option(help="Application version.")] = None,
    commit: Annotated[str | None, typer.Option(help="Commit under test.")] = None,
    automation_tool: Annotated[
        str | None,
        typer.Option(help="Tool for agent_driven or automated runs, e.g. playwright."),
    ] = None,
    requires_approval: Annotated[
        bool, typer.Option(help="Needs a human approval before it runs.")
    ] = False,
) -> None:
    """Create an execution in the 'created' state."""
    repository = _open(project, writable=True)
    try:
        record = create_execution(
            repository,
            execution_type=execution_type,
            executor=executor,
            environment=environment,
            test_case=case,
            plan=plan,
            suite=suite,
            project=project,
            version=version,
            commit=commit,
            automation_tool=automation_tool,
            requires_approval=requires_approval,
        )
    except (ExecutionError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"Created {record.id}  {record.metadata['status']}")


@executions_app.command("move")
def move_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    to: Annotated[str, typer.Option(help="The state to move to.")],
    observed: Annotated[
        str | None, typer.Option(help="Observed result (for passed/failed).")
    ] = None,
    reason: Annotated[
        str | None, typer.Option(help="Reason (blocked, inconclusive, cancelled).")
    ] = None,
    evidence: Annotated[
        list[str] | None, typer.Option(help="EVD id supporting the result.")
    ] = None,
    bug: Annotated[list[str] | None, typer.Option(help="BUG id.")] = None,
    approved_by: Annotated[
        str | None, typer.Option(help="Who approves (awaiting_approval -> running).")
    ] = None,
) -> None:
    """Move an execution to another state, if the lifecycle allows it."""
    repository = _open(project, writable=True)
    try:
        record = move(
            repository,
            execution_id,
            to,
            observed_result=observed,
            reason=reason,
            evidence=evidence or [],
            bugs=bug or [],
            approved_by=approved_by,
        )
    except (InvalidTransition, ExecutionError, StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"{record.id} is now {record.metadata['status']}.")


@executions_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List the executions of a project."""
    repository = _open(project, writable=False)
    try:
        listing = repository.list_records("EXEC")
    except StorageError as error:
        _fail(str(error))
    if not listing.records and not listing.errors:
        typer.echo("No executions yet. Create one with: qa-workbench executions create")
    for record in listing.records:
        meta = record.metadata
        typer.echo(
            f"{record.id}  {meta['status']:<17}  {meta['execution_type']:<15}  "
            f"{meta.get('test_case', '-')}"
        )
    for error in listing.errors:
        typer.echo(f"Warning: {error}", err=True)
    if listing.errors:
        raise typer.Exit(1)


@executions_app.command("show")
def show_command(execution_id: ExecutionArgument, project: ProjectOption) -> None:
    """Show an execution."""
    repository = _open(project, writable=False)
    try:
        record = repository.get(execution_id)
    except StorageError as error:
        _fail(str(error))
    typer.echo(record.body.rstrip())
