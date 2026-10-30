"""``batman release`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab.cli import _client as gitlab_client
from qa_workbench.integrations.gitlab.client import DEFAULT_TOKEN_ENV
from qa_workbench.integrations.gitlab.repository import GitLabRepository
from qa_workbench.projects.errors import ProjectError
from qa_workbench.release.analysis import analyze_release
from qa_workbench.release.records import save_analysis
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.workspace import open_repository

release_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Analyze what a release changed and what to retest.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@release_app.command("analyze")
def analyze_command(
    project: ProjectOption,
    ref: Annotated[str | None, typer.Option(help="Branch, tag, or ref.")] = None,
    since: Annotated[str | None, typer.Option(help="ISO date or time.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=200, help="Commits to read.")] = 30,
    no_merge_requests: Annotated[
        bool, typer.Option("--no-merge-requests", help="Skip merged MRs.")
    ] = False,
    url: Annotated[
        str | None, typer.Option("--url", help="GitLab project URL.")
    ] = None,
    token_env: Annotated[str, typer.Option("--token-env")] = DEFAULT_TOKEN_ENV,
) -> None:
    """Read real commits and merge requests and save the analysis."""
    try:
        repository = open_repository(project, writable=True)
        guard = ActionGuard(load_settings(repository.root), AuditLog(repository.root))
        client = gitlab_client(project, url, token_env)
        guard.authorize(
            ActionRequest(
                "read repository history",
                Category.READ,
                f"commits since {since or '-'} on {ref or 'default branch'}",
                target_url=client.base_url,
                requested_by="release-analysis",
            )
        )
        analysis = analyze_release(
            GitLabRepository(client),
            repository,
            ref=ref,
            since=since,
            limit=limit,
            merge_requests=not no_merge_requests,
        )
        record = save_analysis(repository, analysis)
    except (
        IntegrationError,
        SecurityError,
        AuditError,
        SecuritySettingsError,
        ConfigurationError,
        ProjectError,
        StorageError,
    ) as error:
        _fail(str(error))
    typer.echo(f"Saved {record.id}: risk {analysis.risk_level}.")
    typer.echo(analysis.regression)
    for area in analysis.areas:
        if area.level != "low":
            typer.echo(
                f"  {area.level.upper():<6} {area.area}: {'; '.join(area.reasons)}"
            )


@release_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List saved analyses."""
    try:
        listing = open_repository(project, writable=False).list_records("REL")
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    for record in listing.records:
        typer.echo(
            f"{record.id}  {record.metadata['risk_level']:<6} "
            f"{record.metadata['title']}"
        )
    for problem in listing.errors:
        typer.echo(f"Damaged record: {problem}", err=True)
    if not listing.records and not listing.errors:
        typer.echo("No release analyses yet.")


@release_app.command("show")
def show_command(
    release_id: Annotated[str, typer.Argument(help="REL id.")], project: ProjectOption
) -> None:
    """Show a saved analysis."""
    try:
        record = open_repository(project, writable=False).get(release_id)
    except (ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    typer.echo(record.body)
