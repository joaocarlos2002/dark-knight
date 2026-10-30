"""``qa-workbench suites`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.suites.service import (
    SuiteError,
    add_cases,
    create_suite,
    membership,
    remove_cases,
    summarize,
    verify_suite,
)
from qa_workbench.workspace import open_repository

suites_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Group test cases into reusable suites.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]
SuiteArgument = Annotated[str, typer.Argument(help="Suite id, such as SUITE-001.")]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _open(project: str, *, writable: bool) -> MarkdownRepository:
    try:
        return open_repository(project, writable=writable)
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))


@suites_app.command("create")
def create_command(
    title: Annotated[str, typer.Argument(help="Suite title.")],
    project: ProjectOption,
    suite_type: Annotated[
        str, typer.Option("--type", help="smoke, regression, api, custom, ...")
    ] = "custom",
    description: Annotated[str, typer.Option(help="What the suite is for.")] = "",
    case: Annotated[
        list[str] | None, typer.Option(help="A TC id to include. Repeatable.")
    ] = None,
) -> None:
    """Create a suite as a draft."""
    repository = _open(project, writable=True)
    try:
        suite = create_suite(
            repository,
            title,
            suite_type,
            description=description,
            cases=case or [],
        )
    except (SuiteError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"Created {suite.id}  {suite.metadata['title']}")


@suites_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List the suites of a project with their case counts."""
    repository = _open(project, writable=False)
    try:
        suites = summarize(repository)
    except StorageError as error:
        _fail(str(error))
    if not suites:
        typer.echo("No suites yet. Create one with: qa-workbench suites create")
    for suite in suites:
        typer.echo(
            f"{suite.id}  {suite.status:<8}  {suite.type:<13}  "
            f"{len(suite.cases):>3} cases  {suite.title}"
        )


@suites_app.command("show")
def show_command(suite_id: SuiteArgument, project: ProjectOption) -> None:
    """Show a suite."""
    repository = _open(project, writable=False)
    try:
        record = repository.get(suite_id)
    except StorageError as error:
        _fail(str(error))
    typer.echo(record.body.rstrip())


@suites_app.command("add")
def add_command(
    suite_id: SuiteArgument,
    project: ProjectOption,
    case: Annotated[list[str], typer.Option(help="A TC id to add. Repeatable.")],
) -> None:
    """Add test cases to a suite. A case may belong to several suites."""
    repository = _open(project, writable=True)
    try:
        suite = add_cases(repository, suite_id, case)
    except (SuiteError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"{suite.id} now has {len(suite.metadata['cases'])} cases.")


@suites_app.command("remove")
def remove_command(
    suite_id: SuiteArgument,
    project: ProjectOption,
    case: Annotated[list[str], typer.Option(help="A TC id to remove. Repeatable.")],
) -> None:
    """Remove test cases from a suite. The cases themselves are kept."""
    repository = _open(project, writable=True)
    try:
        suite = remove_cases(repository, suite_id, case)
    except (SuiteError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"{suite.id} now has {len(suite.metadata['cases'])} cases.")


@suites_app.command("membership")
def membership_command(project: ProjectOption) -> None:
    """Show which suites each test case belongs to."""
    repository = _open(project, writable=False)
    try:
        members = membership(repository)
    except StorageError as error:
        _fail(str(error))
    if not members.case_suites:
        typer.echo("No test case belongs to a suite yet.")
    for case_id, suites in members.case_suites.items():
        typer.echo(f"{case_id}  {', '.join(suites)}")


@suites_app.command("verify")
def verify_command(suite_id: SuiteArgument, project: ProjectOption) -> None:
    """Check that the cases of a suite exist and are ready."""
    repository = _open(project, writable=False)
    try:
        result = verify_suite(repository, suite_id)
    except StorageError as error:
        _fail(str(error))
    for case_id in result.missing:
        typer.echo(f"Missing: {case_id} does not exist.", err=True)
    for case_id in result.not_active:
        typer.echo(f"Not active: {case_id} is not approved yet.")
    if not result.ok:
        raise typer.Exit(1)
    typer.echo(f"{suite_id}: every case exists.")
