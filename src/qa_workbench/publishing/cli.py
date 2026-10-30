"""``batman comments`` commands: draft, then publish with approval."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.gitlab.client import (
    DEFAULT_TOKEN_ENV,
    GitLabClient,
    GitLabConnection,
)
from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.publishing.service import (
    CommentError,
    GitLabComments,
    PublishFailed,
    draft_comment,
    publish_comment,
)
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.workspace import open_repository

comments_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Draft issue comments and publish them only with human approval.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]
UrlOption = Annotated[
    str | None,
    typer.Option("--url", help="GitLab project URL. Defaults to the repository."),
]
TokenEnvOption = Annotated[
    str,
    typer.Option("--token-env", help="Environment variable that holds the token."),
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _writer(project: str, url: str | None, token_env: str) -> GitLabComments:
    try:
        opened = ProjectRepository(AppConfig.load().data_dir).open(project)
        source = url or opened.repository
        if not source:
            _fail(f"{project} has no repository URL. Pass --url.")
        connection = GitLabConnection.from_repository_url(source, token_env=token_env)
    except (ConfigurationError, ProjectError, IntegrationError) as error:
        _fail(str(error))
    # Looked up at call time so tests can replace the real HTTP client.
    client = GitLabClient(connection, gitlab_cli.default_gateway())
    return GitLabComments(client, connection.base_url, connection.project_path)


@comments_app.command("draft")
def draft_command(
    issue: Annotated[int, typer.Argument(help="Issue number.")],
    project: ProjectOption,
    author: Annotated[str, typer.Option(help="Who is responsible for the text.")],
    evidence: Annotated[
        list[str] | None, typer.Option(help="EVD id that supports it. Repeatable.")
    ] = None,
    execution: Annotated[str | None, typer.Option(help="EXEC id.")] = None,
    requirement: Annotated[list[str] | None, typer.Option(help="REQ id.")] = None,
    body: Annotated[str | None, typer.Option(help="The comment text.")] = None,
    body_file: Annotated[
        Path | None, typer.Option(help="Read the text from a file.")
    ] = None,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Save a draft. Nothing is sent to the issue."""
    if (body is None) == (body_file is None):
        _fail("Give the text with exactly one of --body or --body-file.")
    try:
        text = body if body is not None else body_file.read_text(encoding="utf-8")  # type: ignore[union-attr]
        root = open_repository(project, writable=True)
        security = load_settings(root.root)
        record = draft_comment(
            root,
            issue=issue,
            body=text,
            author=author,
            writer=_writer(project, url, token_env),
            allowed_hosts=security.allowed_hosts,
            evidence=evidence or (),
            execution=execution,
            requirements=requirement or (),
        )
    except (
        CommentError,
        ConfigurationError,
        ProjectError,
        SecuritySettingsError,
        StorageError,
        OSError,
    ) as error:
        _fail(str(error))
    typer.echo(
        f"Drafted {record.id}. Publish it with `batman comments publish {record.id}`."
    )


@comments_app.command("publish")
def publish_command(
    comment_id: Annotated[str, typer.Argument(help="Comment id, such as COMMENT-001.")],
    project: ProjectOption,
    checked_issue: Annotated[
        bool,
        typer.Option(
            "--checked-issue",
            help="After an unknown outcome: I checked the issue and it is not there.",
        ),
    ] = False,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Publish an approved draft. Without approval, a request is created."""
    try:
        repository = open_repository(project, writable=True)
        guard = ActionGuard(load_settings(repository.root), AuditLog(repository.root))
        record = publish_comment(
            repository,
            comment_id,
            guard=guard,
            writer=_writer(project, url, token_env),
            checked_issue_for_unknown_outcome=checked_issue,
        )
    except PublishFailed as error:
        _fail(f"{error} (recorded as {error.status})")
    except (
        CommentError,
        SecurityError,
        AuditError,
        ConfigurationError,
        ProjectError,
        SecuritySettingsError,
        StorageError,
    ) as error:
        _fail(str(error))
    typer.echo(f"Published {record.id}: {record.metadata['external_url']}")


@comments_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List comments and their state."""
    try:
        listing = open_repository(project, writable=False).list_records("COMMENT")
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    for record in listing.records:
        typer.echo(
            f"{record.id}  {record.metadata['status']:<17} "
            f"issue #{record.metadata['issue']}  by {record.metadata['author']}"
        )
    for problem in listing.errors:
        typer.echo(f"Damaged record: {problem}", err=True)
    if not listing.records and not listing.errors:
        typer.echo("No comments yet.")


@comments_app.command("show")
def show_command(
    comment_id: Annotated[str, typer.Argument(help="Comment id.")],
    project: ProjectOption,
) -> None:
    """Show a comment as it will be (or was) sent."""
    try:
        record = open_repository(project, writable=False).get(comment_id)
    except (ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    meta = record.metadata
    typer.echo(f"{record.id}  {meta['status']}  {meta['issue_url']}")
    typer.echo(
        f"author: {meta['author']}   evidence: {', '.join(meta.get('evidence', []))}"
    )
    typer.echo(record.body)
