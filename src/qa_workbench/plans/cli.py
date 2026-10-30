"""``qa-workbench plans`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.plans.builder import PlanDraft, create_plan, set_selection
from qa_workbench.plans.selection import recommend, verify_plan
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.workspace import open_repository

plans_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Create test plans and choose what to run, with the reasons.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _open(project: str, *, writable: bool) -> MarkdownRepository:
    try:
        return open_repository(project, writable=writable)
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))


@plans_app.command("create")
def create_command(
    title: Annotated[str, typer.Argument(help="Plan title.")],
    project: ProjectOption,
    scope: Annotated[str, typer.Option(help="What the plan covers.")],
    strategy: Annotated[str, typer.Option(help="How testing will be approached.")],
    objective: Annotated[
        list[str] | None, typer.Option(help="Objective. Repeatable.")
    ] = None,
    entry_criterion: Annotated[
        list[str] | None, typer.Option(help="Entry criterion. Repeatable.")
    ] = None,
    exit_criterion: Annotated[
        list[str] | None, typer.Option(help="Exit criterion. Repeatable.")
    ] = None,
    environment: Annotated[
        list[str] | None, typer.Option(help="Environment. Repeatable.")
    ] = None,
    owner: Annotated[list[str] | None, typer.Option(help="Owner. Repeatable.")] = None,
) -> None:
    """Create a test plan as a draft."""
    repository = _open(project, writable=True)
    draft = PlanDraft(
        title=title,
        scope=scope,
        strategy=strategy,
        objectives=objective or [],
        entry_criteria=entry_criterion or [],
        exit_criteria=exit_criterion or [],
        environments=environment or [],
        owners=owner or [],
    )
    try:
        record = create_plan(repository, draft)
    except StorageError as error:
        _fail(str(error))
    typer.echo(f"Created {record.id}  {record.metadata['title']}")


@plans_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List the test plans of a project."""
    repository = _open(project, writable=False)
    try:
        listing = repository.list_records("TP")
    except StorageError as error:
        _fail(str(error))
    if not listing.records and not listing.errors:
        typer.echo("No test plans yet. Create one with: qa-workbench plans create")
    for record in listing.records:
        typer.echo(
            f"{record.id}  {record.metadata['status']:<11}  {record.metadata['title']}"
        )
    for error in listing.errors:
        typer.echo(f"Warning: {error}", err=True)
    if listing.errors:
        raise typer.Exit(1)


@plans_app.command("show")
def show_command(
    plan_id: Annotated[str, typer.Argument(help="Plan id, such as TP-001.")],
    project: ProjectOption,
) -> None:
    """Show a test plan."""
    repository = _open(project, writable=False)
    try:
        record = repository.get(plan_id)
    except StorageError as error:
        _fail(str(error))
    typer.echo(record.body.rstrip())


@plans_app.command("recommend")
def recommend_command(
    project: ProjectOption,
    requirement: Annotated[
        list[str] | None,
        typer.Option(help="A changed requirement (REQ id). Repeatable."),
    ] = None,
    budget: Annotated[
        int | None, typer.Option(help="Available time, in minutes.")
    ] = None,
    save_to: Annotated[
        str | None, typer.Option(help="Plan id to store the selection on.")
    ] = None,
) -> None:
    """Recommend which test cases to run, with the reason for each decision."""
    repository = _open(project, writable=save_to is not None)
    try:
        recommendation = recommend(
            repository,
            changed_requirements=requirement or [],
            time_budget_minutes=budget,
        )
    except (StorageError, ValueError) as error:
        _fail(str(error))
    for item in recommendation.items:
        typer.echo(f"{item.decision.upper():<7} {item.id}")
        for reason in item.reasons:
            typer.echo(f"          {reason.factor}: {reason.detail}")
    included = len(recommendation.included())
    typer.echo(
        f"{included} of {len(recommendation.items)} cases included"
        + (f", {recommendation.minutes_used} min estimated." if budget else ".")
    )
    for note in recommendation.notes:
        typer.echo(f"Not considered - {note}")
    if save_to is not None:
        try:
            set_selection(repository, save_to, recommendation.to_fields())
        except StorageError as error:
            _fail(str(error))
        typer.echo(f"Selection stored on {save_to}. Edit it there if needed.")


@plans_app.command("verify")
def verify_command(
    plan_id: Annotated[str, typer.Argument(help="Plan id, such as TP-001.")],
    project: ProjectOption,
) -> None:
    """Check that the selection of a plan exists and is ready to run."""
    repository = _open(project, writable=False)
    try:
        result = verify_plan(repository, plan_id)
    except StorageError as error:
        _fail(str(error))
    for record_id in result.missing:
        typer.echo(f"Missing: {record_id} does not exist.", err=True)
    for record_id in result.not_ready:
        typer.echo(f"Not ready: {record_id} is included but not active.", err=True)
    for record_id in result.unverifiable:
        typer.echo(f"Not checked: {record_id} (this kind is not stored here).")
    if not result.ok:
        raise typer.Exit(1)
    typer.echo(f"{plan_id}: the selection is sound.")
