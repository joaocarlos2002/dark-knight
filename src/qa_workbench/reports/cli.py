"""``qa-workbench reports`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.reports.execution import render_execution_report
from qa_workbench.reports.traceability import build_graph, trace
from qa_workbench.reports.writer import (
    is_execution_report_stale,
    render_traceability_report,
    write_execution_report,
    write_traceability_report,
)
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.workspace import open_repository

reports_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Execution reports and traceability from requirement to evidence.",
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


@reports_app.command("execution")
def execution_command(
    execution_id: Annotated[str, typer.Argument(help="Execution id, e.g. EXEC-001.")],
    project: ProjectOption,
    save: Annotated[
        bool, typer.Option("--save", help="Save it under the project's reports.")
    ] = False,
) -> None:
    """Show (and optionally save) the report of an execution."""
    repository = _open(project, writable=save)
    try:
        if save:
            path = write_execution_report(repository, execution_id)
            typer.echo(f"Saved {path}")
            return
        typer.echo(render_execution_report(repository, execution_id).rstrip())
        if is_execution_report_stale(repository, execution_id):
            typer.echo(
                "Note: the saved report is out of date; save it again.", err=True
            )
    except StorageError as error:
        _fail(str(error))


@reports_app.command("traceability")
def traceability_command(
    project: ProjectOption,
    save: Annotated[
        bool, typer.Option("--save", help="Save it under the project's reports.")
    ] = False,
) -> None:
    """Show (and optionally save) the requirement-to-execution matrix."""
    repository = _open(project, writable=save)
    try:
        if save:
            typer.echo(f"Saved {write_traceability_report(repository)}")
            return
        typer.echo(render_traceability_report(repository).rstrip())
    except StorageError as error:
        _fail(str(error))


@reports_app.command("trace")
def trace_command(
    record_id: Annotated[str, typer.Argument(help="Any record id, e.g. REQ-001.")],
    project: ProjectOption,
) -> None:
    """Show what a record is connected to, upstream and downstream."""
    repository = _open(project, writable=False)
    try:
        graph = build_graph(repository)
        result = trace(graph, record_id)
    except (StorageError, ValueError) as error:
        _fail(str(error))
    if not graph.exists(record_id):
        _fail(f"{record_id} was not found.")
    if not result.upstream and not result.downstream:
        typer.echo(f"{record_id} is not linked to any other record.")
    for label, group in (
        ("Upstream", result.upstream),
        ("Downstream", result.downstream),
    ):
        for kind, ids in group.items():
            typer.echo(f"{label} {kind}: {', '.join(ids)}")
