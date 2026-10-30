"""``qa-workbench evidence`` commands."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.workspace import open_repository

evidence_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Register evidence files and check their integrity.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _store(project: str, *, writable: bool) -> EvidenceStore:
    try:
        return EvidenceStore(open_repository(project, writable=writable))
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))


@evidence_app.command("add")
def add_command(
    file: Annotated[Path, typer.Argument(help="The file to register (it is copied).")],
    project: ProjectOption,
    source: Annotated[str, typer.Option(help="Where it came from, e.g. manual.")],
    description: Annotated[str, typer.Option(help="What it shows.")],
    step: Annotated[str | None, typer.Option(help="The step it belongs to.")] = None,
    execution: Annotated[str | None, typer.Option(help="EXEC id.")] = None,
    source_url: Annotated[str | None, typer.Option(help="http(s) URL.")] = None,
    derived_from: Annotated[
        str | None, typer.Option(help="EVD id of the original, for an annotated copy.")
    ] = None,
) -> None:
    """Copy a file into the project and record its SHA-256."""
    store = _store(project, writable=True)
    try:
        record = store.register(
            file,
            source=source,
            description=description,
            step=step,
            execution=execution,
            source_url=source_url,
            derived_from=derived_from,
        )
    except (StorageError, ValueError) as error:
        _fail(str(error))
    typer.echo(f"Registered {record.id}  sha256 {record.metadata['sha256'][:12]}...")


@evidence_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List registered evidence."""
    store = _store(project, writable=False)
    try:
        listing = store.list_records()
    except StorageError as error:
        _fail(str(error))
    if not listing.records and not listing.errors:
        typer.echo("No evidence yet. Register some with: qa-workbench evidence add")
    for record in listing.records:
        meta = record.metadata
        typer.echo(
            f"{record.id}  {meta['sha256'][:12]}  {meta['media_type']:<18}  "
            f"{meta['description']}"
        )
    for error in listing.errors:
        typer.echo(f"Warning: {error}", err=True)
    if listing.errors:
        raise typer.Exit(1)


@evidence_app.command("verify")
def verify_command(
    project: ProjectOption,
    evidence_id: Annotated[
        str | None, typer.Argument(help="One EVD id; all evidence when omitted.")
    ] = None,
) -> None:
    """Check files and records against their recorded hashes."""
    store = _store(project, writable=False)
    try:
        problems = (
            {evidence_id: store.verify(evidence_id)}
            if evidence_id
            else store.verify_all()
        )
    except StorageError as error:
        _fail(str(error))
    problems = {key: value for key, value in problems.items() if value}
    for key, found in problems.items():
        for problem in found:
            typer.echo(f"{key}: {problem}", err=True)
    if problems:
        raise typer.Exit(1)
    typer.echo("All evidence is intact.")
