"""``batman edits`` commands: fetch and list the startup edits."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.edits.service import EditsError, fetch_edits, find_edits

edits_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Fetch and inspect the edits played before the workbench opens.",
)


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _config() -> AppConfig:
    try:
        return AppConfig.load()
    except ConfigurationError as error:
        _fail(str(error))


@edits_app.command("fetch")
def fetch_command(
    repo: Annotated[
        str | None,
        typer.Option("--repo", help="GitHub repository with the edits, owner/name."),
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option("--ref", help="Tag, branch, or commit to download."),
    ] = None,
    directory: Annotated[
        Path | None,
        typer.Option("--dir", help="Folder that receives the videos."),
    ] = None,
    sha256: Annotated[
        str | None,
        typer.Option("--sha256", help="Expected SHA-256 of the downloaded archive."),
    ] = None,
) -> None:
    """Download the startup edits from a GitHub repository."""
    config = _config()
    target_repo = repo or config.edits_repo
    if not target_repo:
        _fail(
            "No edits repository configured. Pass --repo owner/name or set "
            "[startup] repo in config.toml."
        )
    target_dir = directory or config.edits_dir
    try:
        result = fetch_edits(
            repo=target_repo,
            ref=ref or config.edits_ref,
            destination=target_dir,
            sha256=sha256 or config.edits_sha256,
        )
    except EditsError as error:
        _fail(str(error))
    typer.echo(f"Fetched {result.count} edit(s) into {result.destination}")
    for video in result.videos:
        typer.echo(f"  {video.name}")


@edits_app.command("list")
def list_command(
    directory: Annotated[
        Path | None,
        typer.Option("--dir", help="Folder with the videos."),
    ] = None,
) -> None:
    """List the edits that the splash can choose from."""
    config = _config()
    target_dir = directory or config.edits_dir
    videos = find_edits(target_dir)
    if not videos:
        typer.echo(f"No edits in {target_dir}.")
        return
    typer.echo(f"{len(videos)} edit(s) in {target_dir}:")
    for video in videos:
        typer.echo(f"  {video.name}")
