"""``qa-workbench executions`` commands."""

from datetime import timedelta
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.executions.recording import (
    check_preconditions,
    finish_step,
    start_step,
)
from qa_workbench.executions.recovery import (
    find_interrupted,
    record_correction,
    recover,
    rerun,
)
from qa_workbench.executions.schema import EXECUTION_TYPES, FAILURE_TYPES
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
    failure_type: Annotated[
        str | None,
        typer.Option(help=f"Why it failed: {', '.join(sorted(FAILURE_TYPES))}."),
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
            failure_type=failure_type,
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


@executions_app.command("step-start")
def step_start_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    number: Annotated[int, typer.Option(help="Step number, starting at 1.")],
    action: Annotated[str, typer.Option(help="What is about to be done.")],
) -> None:
    """Save a step as in progress, before carrying it out."""
    repository = _open(project, writable=True)
    try:
        start_step(repository, execution_id, number, action)
    except (ExecutionError, StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"{execution_id} step {number} started.")


@executions_app.command("step-finish")
def step_finish_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    number: Annotated[int, typer.Option(help="The step in progress.")],
    outcome: Annotated[
        str, typer.Option(help="passed, failed, blocked, skipped, or interrupted.")
    ],
    observed: Annotated[str, typer.Option(help="What was observed.")] = "",
    evidence: Annotated[
        list[str] | None, typer.Option(help="EVD id. Repeatable.")
    ] = None,
    failure_type: Annotated[
        str | None, typer.Option(help="Required when the step failed.")
    ] = None,
) -> None:
    """Complete the step that is in progress."""
    repository = _open(project, writable=True)
    try:
        finish_step(
            repository,
            execution_id,
            number,
            outcome,
            observed=observed,
            evidence=evidence or [],
            failure_type=failure_type,
        )
    except (ExecutionError, StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"{execution_id} step {number}: {outcome}.")


@executions_app.command("preconditions")
def preconditions_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    met: Annotated[
        list[str] | None, typer.Option(help="A precondition that held. Repeatable.")
    ] = None,
    unmet: Annotated[
        list[str] | None, typer.Option(help="A precondition that did not. Repeatable.")
    ] = None,
) -> None:
    """Record which preconditions were verified."""
    repository = _open(project, writable=True)
    checks = [(text, True) for text in met or []] + [
        (text, False) for text in unmet or []
    ]
    try:
        check_preconditions(repository, execution_id, checks)
    except (ExecutionError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"{execution_id}: {len(checks)} preconditions recorded.")


@executions_app.command("interrupted")
def interrupted_command(
    project: ProjectOption,
    idle_minutes: Annotated[
        int, typer.Option(help="Minutes without activity before a run counts.")
    ] = 30,
) -> None:
    """List running executions that seem to have been cut short."""
    repository = _open(project, writable=False)
    try:
        found = find_interrupted(repository, idle_for=timedelta(minutes=idle_minutes))
    except (StorageError, ValueError) as error:
        _fail(str(error))
    if not found:
        typer.echo("No interrupted executions.")
    for item in found:
        open_step = (
            f", step {item.step_in_progress} was in progress"
            if item.step_in_progress
            else ""
        )
        typer.echo(
            f"{item.id}  last activity {item.last_activity.isoformat()}, "
            f"{item.steps_done} steps done{open_step}"
        )


@executions_app.command("recover")
def recover_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    action: Annotated[str, typer.Option(help="resume or abandon.")],
    note: Annotated[str, typer.Option(help="What happened.")],
) -> None:
    """Resume or abandon an interrupted execution."""
    repository = _open(project, writable=True)
    try:
        record = recover(repository, execution_id, action=action, note=note)
    except (ExecutionError, StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"{record.id} is now {record.metadata['status']}.")


@executions_app.command("rerun")
def rerun_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    executor: Annotated[
        str | None, typer.Option(help="Executor of the new run.")
    ] = None,
) -> None:
    """Start a new execution that repeats a finished one."""
    repository = _open(project, writable=True)
    try:
        record = rerun(repository, execution_id, executor=executor)
    except (ExecutionError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"Created {record.id} (rerun of {execution_id}).")


@executions_app.command("correct")
def correct_command(
    execution_id: ExecutionArgument,
    project: ProjectOption,
    author: Annotated[str, typer.Option(help="Who is correcting.")],
    justification: Annotated[str, typer.Option(help="Why.")],
    addition: Annotated[
        bool, typer.Option(help="Record an addition instead of a correction.")
    ] = False,
) -> None:
    """Record a correction to a finalized execution as a separate event."""
    repository = _open(project, writable=True)
    try:
        event = record_correction(
            repository,
            execution_id,
            author=author,
            justification=justification,
            addition=addition,
        )
    except (StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"{execution_id}: {event.kind} #{event.sequence} recorded.")


@executions_app.command("history")
def history_command(execution_id: ExecutionArgument, project: ProjectOption) -> None:
    """Show the history events of an execution and check its integrity."""
    repository = _open(project, writable=False)
    try:
        events = repository.history(execution_id)
        problems = repository.verify(execution_id)
    except StorageError as error:
        _fail(str(error))
    if not events:
        typer.echo("No history: the execution is not finalized.")
    for event in events:
        typer.echo(
            f"{event.sequence}. {event.timestamp.isoformat()}  {event.kind}  "
            f"{event.author}: {event.justification}"
        )
    for problem in problems:
        typer.echo(f"Integrity problem: {problem}", err=True)
    if problems:
        raise typer.Exit(1)
