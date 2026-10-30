"""``qa-workbench requirements`` commands."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.requirements.coverage import coverage
from qa_workbench.requirements.importer import (
    RequirementImportError,
    import_requirements,
)
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.workspace import open_repository

requirements_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Import, list, and check coverage of requirements.",
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


@requirements_app.command("import")
def import_command(
    source: Annotated[Path, typer.Argument(help="A .md or .txt file.")],
    project: ProjectOption,
    author: Annotated[
        str | None, typer.Option(help="Author for requirements that name none.")
    ] = None,
    source_version: Annotated[
        str | None, typer.Option(help="Version label of the source document.")
    ] = None,
    generated_by: Annotated[
        str | None,
        typer.Option(help="Provider or model, if the source is AI-generated."),
    ] = None,
) -> None:
    """Import requirements from a Markdown or text file."""
    repository = _open(project, writable=True)
    try:
        report = import_requirements(
            repository,
            source,
            author=author,
            source_version=source_version,
            generated_by=generated_by,
        )
    except (RequirementImportError, StorageError) as error:
        _fail(str(error))
    for record in report.created:
        typer.echo(f"Created {record.id}  {record.metadata['title']}")
    for record_id in report.skipped:
        typer.echo(f"Skipped {record_id} (already imported from this file)")
    for issue in report.issues:
        typer.echo(f"Problem {issue.location}: {issue.message}", err=True)
    typer.echo(
        f"{len(report.created)} created, {len(report.skipped)} skipped, "
        f"{len(report.issues)} with problems."
    )
    if report.issues:
        raise typer.Exit(1)


@requirements_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List the requirements of a project."""
    repository = _open(project, writable=False)
    try:
        listing = repository.list_records("REQ")
    except StorageError as error:
        _fail(str(error))
    if not listing.records and not listing.errors:
        typer.echo(
            "No requirements yet. Import some with: qa-workbench requirements import"
        )
    for record in listing.records:
        metadata = record.metadata
        priority = metadata.get("priority", "-")
        typer.echo(
            f"{record.id}  {metadata['status']:<10}  {priority:<6}  {metadata['title']}"
        )
    for error in listing.errors:
        typer.echo(f"Warning: {error}", err=True)
    if listing.errors:
        raise typer.Exit(1)


@requirements_app.command("coverage")
def coverage_command(project: ProjectOption) -> None:
    """Show which requirements have related test cases."""
    repository = _open(project, writable=False)
    try:
        report = coverage(repository)
    except StorageError as error:
        _fail(str(error))
    for item in report:
        mark = "covered  " if item.covered else "UNCOVERED"
        cases = ", ".join(item.cases) or "no test cases"
        typer.echo(f"{item.id}  {mark}  {item.title}  [{cases}]")
        for missing in item.missing_cases:
            typer.echo(f"  Warning: {missing} is listed but does not exist.", err=True)
    uncovered = sum(1 for item in report if not item.covered)
    typer.echo(f"{len(report) - uncovered} of {len(report)} requirements covered.")
