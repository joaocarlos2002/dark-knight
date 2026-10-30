"""``qa-workbench cases`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.workspace import open_repository

cases_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Create, list, and show test cases.",
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


def _step(text: str) -> Step:
    action, separator, expected = text.partition("=>")
    return Step(action.strip(), expected.strip() if separator else "")


@cases_app.command("create")
def create_command(
    title: Annotated[str, typer.Argument(help="Short, objective title.")],
    project: ProjectOption,
    objective: Annotated[str, typer.Option(help="What the case validates.")],
    step: Annotated[
        list[str] | None,
        typer.Option(help="A step, optionally 'action => expected'. Repeatable."),
    ] = None,
    expected_result: Annotated[str, typer.Option(help="Final expected result.")] = "",
    precondition: Annotated[
        list[str] | None, typer.Option(help="Precondition. Repeatable.")
    ] = None,
    requirement: Annotated[
        list[str] | None, typer.Option(help="Related REQ id. Repeatable.")
    ] = None,
    priority: Annotated[str, typer.Option(help="high, medium, or low.")] = "medium",
    case_type: Annotated[str, typer.Option("--type", help="Kind of test.")] = (
        "functional"
    ),
    tag: Annotated[list[str] | None, typer.Option(help="Tag. Repeatable.")] = None,
    author: Annotated[str | None, typer.Option(help="Author of the case.")] = None,
) -> None:
    """Create a test case as a draft."""
    repository = _open(project, writable=True)
    draft = TestCaseDraft(
        title=title,
        objective=objective,
        steps=[_step(text) for text in step or []],
        expected_result=expected_result,
        preconditions=precondition or [],
        requirements=requirement or [],
        priority=priority,
        type=case_type,
        tags=tag or [],
        author=author,
    )
    try:
        record = create_test_case(repository, draft)
    except StorageError as error:
        _fail(str(error))
    typer.echo(f"Created {record.id}  {record.metadata['title']}")


@cases_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List the test cases of a project."""
    repository = _open(project, writable=False)
    try:
        listing = repository.list_records("TC")
    except StorageError as error:
        _fail(str(error))
    if not listing.records and not listing.errors:
        typer.echo("No test cases yet. Create one with: qa-workbench cases create")
    for record in listing.records:
        meta = record.metadata
        typer.echo(
            f"{record.id}  {meta['status']:<10}  {meta['priority']:<6}  "
            f"{meta['type']:<12}  {meta['title']}"
        )
    for error in listing.errors:
        typer.echo(f"Warning: {error}", err=True)
    if listing.errors:
        raise typer.Exit(1)


@cases_app.command("show")
def show_command(
    case_id: Annotated[str, typer.Argument(help="Test case id.")],
    project: ProjectOption,
) -> None:
    """Show a test case."""
    repository = _open(project, writable=False)
    try:
        record = repository.get(case_id)
    except StorageError as error:
        _fail(str(error))
    typer.echo(record.body.rstrip())
