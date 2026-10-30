"""``qa-workbench project`` commands."""

from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.models import Environment, Project
from qa_workbench.projects.repository import ProjectRepository

project_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Create, list, open, and archive projects.",
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _repository() -> ProjectRepository:
    try:
        return ProjectRepository(AppConfig.load().data_dir)
    except ConfigurationError as error:
        _fail(str(error))


def _pairs(values: list[str], option: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for value in values:
        name, separator, rest = value.partition("=")
        if not separator or not name.strip() or not rest.strip():
            raise typer.BadParameter(
                f"expected NAME=VALUE, got {value!r}", param_hint=option
            )
        pairs.append((name.strip(), rest.strip()))
    return pairs


def _row(project: Project) -> str:
    return f"{project.id}  {project.status.value:<8}  {project.name}"


@project_app.command("create")
def create(
    name: Annotated[str, typer.Argument(help="Project name.")],
    description: Annotated[str, typer.Option(help="Short description.")] = "",
    repository: Annotated[str, typer.Option(help="Repository, e.g. owner/name.")] = "",
    directory: Annotated[str, typer.Option(help="Local project directory.")] = "",
    environment: Annotated[
        list[str] | None,
        typer.Option(help="Authorized environment as NAME=URL. Repeatable."),
    ] = None,
    framework: Annotated[
        list[str] | None, typer.Option(help="Framework. Repeatable.")
    ] = None,
    language: Annotated[
        list[str] | None, typer.Option(help="Language. Repeatable.")
    ] = None,
    command: Annotated[
        list[str] | None,
        typer.Option(help="Project command as NAME=COMMAND. Repeatable."),
    ] = None,
) -> None:
    """Create a project."""
    try:
        environments = [
            Environment(name=name_, url=url)
            for name_, url in _pairs(environment or [], "--environment")
        ]
    except ValidationError as error:
        raise typer.BadParameter(str(error), param_hint="--environment") from error
    try:
        project = _repository().create(
            name,
            description=description,
            repository=repository,
            directory=directory,
            environments=environments,
            frameworks=framework or [],
            languages=language or [],
            commands=dict(_pairs(command or [], "--command")),
        )
    except ProjectError as error:
        _fail(str(error))
    typer.echo(f"Created {_row(project)}")


@project_app.command("list")
def list_projects(
    all_: Annotated[
        bool, typer.Option("--all", help="Include archived projects.")
    ] = False,
) -> None:
    """List projects."""
    listing = _repository().list_projects(include_archived=all_)
    if not listing.projects and not listing.errors:
        typer.echo("No projects yet. Create one with: qa-workbench project create NAME")
    for project in listing.projects:
        typer.echo(_row(project))
    for error in listing.errors:
        typer.echo(f"Warning: {error}", err=True)
    if listing.errors:
        raise typer.Exit(1)


@project_app.command("show")
def show(project_id: Annotated[str, typer.Argument(help="Project id.")]) -> None:
    """Open a project and show its details."""
    try:
        project = _repository().open(project_id)
    except ProjectError as error:
        _fail(str(error))
    typer.echo(_row(project))
    typer.echo(f"Created      {project.created_at.isoformat()}")
    typer.echo(f"Updated      {project.updated_at.isoformat()}")
    for label, value in (
        ("Description", project.description),
        ("Repository", project.repository),
        ("Directory", project.directory),
        ("Frameworks", ", ".join(project.frameworks)),
        ("Languages", ", ".join(project.languages)),
    ):
        if value:
            typer.echo(f"{label:<12} {value}")
    for item in project.environments:
        typer.echo(f"Environment  {item.name} {item.url}")
    for name, value in project.commands.items():
        typer.echo(f"Command      {name}: {value}")


@project_app.command("archive")
def archive(project_id: Annotated[str, typer.Argument(help="Project id.")]) -> None:
    """Archive a project. Its files are kept."""
    try:
        project = _repository().archive(project_id)
    except ProjectError as error:
        _fail(str(error))
    typer.echo(f"Archived {_row(project)}")
