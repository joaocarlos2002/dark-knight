"""``batman bugs`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.bughunt.schema import CLASSIFICATIONS, SUSPECTED
from qa_workbench.bughunt.service import BugError, reclassify, record_finding
from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.workspace import open_repository

bugs_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Record exploratory findings; a defect is confirmed only with evidence.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]
CLASSES = ", ".join(CLASSIFICATIONS)


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@bugs_app.command("record")
def record_command(
    title: Annotated[str, typer.Argument(help="Short, objective title.")],
    project: ProjectOption,
    environment: Annotated[str, typer.Option(help="Environment and version.")],
    found_by: Annotated[str, typer.Option(help="Who found it.")],
    classification: Annotated[
        str, typer.Option(help=f"One of: {CLASSES}.")
    ] = SUSPECTED,
    step: Annotated[list[str] | None, typer.Option(help="A step. Repeatable.")] = None,
    expected: Annotated[str, typer.Option(help="Expected result.")] = "",
    observed: Annotated[str, typer.Option(help="Observed result.")] = "",
    evidence: Annotated[list[str] | None, typer.Option(help="EVD id.")] = None,
    attempts: Annotated[int, typer.Option(min=0, help="Times tried.")] = 1,
    reproductions: Annotated[int, typer.Option(min=0, help="Times it happened.")] = 0,
    context: Annotated[str, typer.Option(help="Where and what you were doing.")] = "",
    impact: Annotated[str, typer.Option(help="Who or what it affects.")] = "",
    severity: Annotated[str | None, typer.Option(help="Proposed severity.")] = None,
    reason: Annotated[str, typer.Option(help="Why, for a false positive.")] = "",
    environment_issue: Annotated[
        str, typer.Option(help="What failed in the environment.")
    ] = "",
    execution: Annotated[str | None, typer.Option(help="EXEC id.")] = None,
    limitations: Annotated[str, typer.Option(help="What could not be observed.")] = "",
) -> None:
    """Record a finding. `reproduced` is refused without enough evidence."""
    try:
        repository = open_repository(project, writable=True)
        record = record_finding(
            repository,
            title=title,
            environment=environment,
            found_by=found_by,
            classification=classification,
            steps=step or (),
            expected=expected,
            observed=observed,
            evidence=evidence or (),
            attempts=attempts,
            reproductions=reproductions,
            context=context,
            impact=impact,
            severity=severity,
            reason=reason,
            environment_issue=environment_issue,
            execution=execution,
            limitations=limitations,
        )
    except (BugError, ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"Recorded {record.id} as {record.metadata['status']}.")


@bugs_app.command("reclassify")
def reclassify_command(
    bug_id: Annotated[str, typer.Argument(help="BUG id.")],
    classification: Annotated[str, typer.Argument(help=f"One of: {CLASSES}.")],
    project: ProjectOption,
    by: Annotated[str, typer.Option(help="Who is deciding.")],
    why: Annotated[str, typer.Option(help="Justification.")],
    attempts: Annotated[int | None, typer.Option(min=0)] = None,
    reproductions: Annotated[int | None, typer.Option(min=0)] = None,
    reason: Annotated[str, typer.Option(help="Reason, for a false positive.")] = "",
) -> None:
    """Change the classification, keeping who changed it and why."""
    try:
        record = reclassify(
            open_repository(project, writable=True),
            bug_id,
            classification,
            by=by,
            justification=why,
            attempts=attempts,
            reproductions=reproductions,
            reason=reason,
        )
    except (BugError, ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"{record.id} is now {record.metadata['status']}.")


@bugs_app.command("list")
def list_command(
    project: ProjectOption,
    classification: Annotated[
        str | None, typer.Option(help=f"One of: {CLASSES}.")
    ] = None,
) -> None:
    """List findings."""
    try:
        listing = open_repository(project, writable=False).list_records(
            "BUG", status=classification
        )
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    for record in listing.records:
        meta = record.metadata
        typer.echo(
            f"{record.id}  {meta['status']:<23} "
            f"{meta.get('reproductions', 0)}/{meta.get('attempts', 0)}  {meta['title']}"
        )
    for problem in listing.errors:
        typer.echo(f"Damaged record: {problem}", err=True)
    if not listing.records and not listing.errors:
        typer.echo("No findings.")


@bugs_app.command("show")
def show_command(
    bug_id: Annotated[str, typer.Argument(help="BUG id.")], project: ProjectOption
) -> None:
    """Show a finding."""
    try:
        record = open_repository(project, writable=False).get(bug_id)
    except (ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    typer.echo(record.body)
