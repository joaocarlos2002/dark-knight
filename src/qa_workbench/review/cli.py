"""``qa-workbench review`` commands."""

from enum import StrEnum
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.review.service import ReviewError, ReviewService
from qa_workbench.storage.errors import StorageError
from qa_workbench.workspace import open_repository, review_policies

review_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Human review of AI-generated requirements and test cases.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]


class Decision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes-requested"


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _service(project: str, *, writable: bool) -> ReviewService:
    try:
        repository = open_repository(project, writable=writable)
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    return ReviewService(repository, review_policies())


@review_app.command("pending")
def pending_command(project: ProjectOption) -> None:
    """List AI-generated records waiting for a human decision."""
    service = _service(project, writable=False)
    try:
        records = service.pending()
    except StorageError as error:
        _fail(str(error))
    if not records:
        typer.echo("Nothing is waiting for review.")
    for record in records:
        meta = record.metadata
        typer.echo(
            f"{record.id}  {meta['status']:<10}  {meta['generated_by']:<12}  "
            f"{meta['title']}"
        )


@review_app.command("submit")
def submit_command(
    record_id: Annotated[str, typer.Argument(help="Record id, such as REQ-001.")],
    project: ProjectOption,
) -> None:
    """Submit a draft for review."""
    service = _service(project, writable=True)
    try:
        record = service.submit(record_id)
    except (ReviewError, StorageError) as error:
        _fail(str(error))
    typer.echo(f"{record.id} is now {record.metadata['status']}.")


@review_app.command("decide")
def decide_command(
    record_id: Annotated[str, typer.Argument(help="Record id, such as REQ-001.")],
    project: ProjectOption,
    decision: Annotated[Decision, typer.Option(help="The reviewer's decision.")],
    reviewer: Annotated[str, typer.Option(help="Name of the human reviewer.")],
    comment: Annotated[str, typer.Option(help="Why.")] = "",
) -> None:
    """Record a human decision on a record that is in review."""
    service = _service(project, writable=True)
    try:
        record = service.decide(
            record_id, reviewer, decision.value.replace("-", "_"), comment
        )
    except (ReviewError, StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"{record.id} is now {record.metadata['status']}.")
