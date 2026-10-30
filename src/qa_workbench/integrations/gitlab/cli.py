"""``batman gitlab`` commands (read-only)."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.core.secrets import redact_secrets
from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab.client import (
    DEFAULT_TOKEN_ENV,
    GitLabClient,
    GitLabConnection,
)
from qa_workbench.integrations.gitlab.issues import GitLabIssues
from qa_workbench.integrations.gitlab.pipelines import GitLabPipelines
from qa_workbench.integrations.gitlab.repository import GitLabRepository
from qa_workbench.integrations.http import HttpGateway, HttpxGateway
from qa_workbench.integrations.untrusted import fence
from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.repository import ProjectRepository

gitlab_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Read issues, commits, merge requests, and pipelines from GitLab.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]
UrlOption = Annotated[
    str | None,
    typer.Option(
        "--url",
        help="GitLab project URL. Defaults to the repository of the project.",
    ),
]
TokenEnvOption = Annotated[
    str,
    typer.Option("--token-env", help="Environment variable that holds the token."),
]
LimitOption = Annotated[int, typer.Option("--limit", min=1, max=500)]


def default_gateway() -> HttpGateway:
    """The real HTTP client. Tests replace this so nothing touches the network."""
    return HttpxGateway()


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _client(project: str, url: str | None, token_env: str) -> GitLabClient:
    try:
        config = AppConfig.load()
        opened = ProjectRepository(config.data_dir).open(project)
        source = url or opened.repository
        if not source:
            _fail(
                f"{project} has no repository URL. Pass --url "
                "https://gitlab.example.com/group/app"
            )
        connection = GitLabConnection.from_repository_url(source, token_env=token_env)
    except (ConfigurationError, ProjectError, IntegrationError) as error:
        _fail(str(error))
    return GitLabClient(connection, default_gateway())


def _run(action):
    try:
        return action()
    except IntegrationError as error:
        _fail(str(error))


def _seconds(value: float | None) -> str:
    return f"{value:.0f}s" if value is not None else "-"


@gitlab_app.command("issues")
def issues_command(
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
    state: Annotated[str, typer.Option(help="opened, closed, or all.")] = "opened",
    label: Annotated[list[str] | None, typer.Option(help="Repeatable.")] = None,
    limit: LimitOption = 20,
) -> None:
    """List issues."""
    source = GitLabIssues(_client(project, url, token_env))
    found = _run(
        lambda: source.list_issues(state=state, labels=tuple(label or ()), limit=limit)
    )
    for issue in found:
        labels = ", ".join(issue.labels) or "-"
        typer.echo(f"#{issue.iid:<5} {issue.state:<7} {issue.title}  [{labels}]")
    if not found:
        typer.echo("No issues match.")


@gitlab_app.command("issue")
def issue_command(
    iid: Annotated[int, typer.Argument(help="Issue number.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Show an issue with its comments. Its text is marked as untrusted data."""
    source = GitLabIssues(_client(project, url, token_env))
    issue = _run(lambda: source.get_issue(iid))
    where = f"GitLab issue #{iid}"
    typer.echo(f"#{issue.iid} {issue.state}  {issue.url}")
    typer.echo(f"Labels: {', '.join(issue.labels) or '-'}   Author: {issue.author}")
    typer.echo(fence(f"{issue.title}\n\n{issue.description}", source=where))
    for note in issue.notes:
        if not note.system:
            typer.echo(fence(note.body, source=f"{where} comment by {note.author}"))


@gitlab_app.command("commits")
def commits_command(
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
    ref: Annotated[str | None, typer.Option(help="Branch, tag, or ref.")] = None,
    since: Annotated[str | None, typer.Option(help="ISO date or time.")] = None,
    limit: LimitOption = 20,
) -> None:
    """List recent commits."""
    source = GitLabRepository(_client(project, url, token_env))
    for commit in _run(lambda: source.list_commits(ref=ref, since=since, limit=limit)):
        typer.echo(
            f"{commit.sha[:10]}  {commit.date[:10]}  {commit.author}: {commit.title}"
        )


@gitlab_app.command("commit")
def commit_command(
    sha: Annotated[str, typer.Argument(help="Commit SHA.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Show a commit and the files it changed."""
    source = GitLabRepository(_client(project, url, token_env))
    commit = _run(lambda: source.get_commit(sha))
    typer.echo(f"{commit.sha}  {commit.author}  {commit.date}")
    typer.echo(fence(commit.title, source=f"GitLab commit {commit.sha[:10]}"))
    for path in commit.files:
        typer.echo(f"  {path}")


@gitlab_app.command("mrs")
def merge_requests_command(
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
    state: Annotated[
        str, typer.Option(help="opened, merged, closed, or all.")
    ] = "opened",
    limit: LimitOption = 20,
) -> None:
    """List merge requests."""
    source = GitLabRepository(_client(project, url, token_env))
    for mr in _run(lambda: source.list_merge_requests(state=state, limit=limit)):
        typer.echo(
            f"!{mr.iid:<5} {mr.state:<7} "
            f"{mr.source_branch} -> {mr.target_branch}  {mr.title}"
        )


@gitlab_app.command("mr")
def merge_request_command(
    iid: Annotated[int, typer.Argument(help="Merge request number.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Show a merge request and the files it changes."""
    source = GitLabRepository(_client(project, url, token_env))
    mr = _run(lambda: source.get_merge_request(iid))
    typer.echo(
        f"!{mr.iid} {mr.state}  {mr.source_branch} -> {mr.target_branch}  {mr.url}"
    )
    typer.echo(fence(mr.title, source=f"GitLab merge request !{mr.iid}"))
    for path in mr.files:
        typer.echo(f"  {path}")


@gitlab_app.command("pipelines")
def pipelines_command(
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
    ref: Annotated[str | None, typer.Option(help="Branch or tag.")] = None,
    status: Annotated[str | None, typer.Option(help="For example failed.")] = None,
    limit: LimitOption = 20,
) -> None:
    """List pipelines."""
    source = GitLabPipelines(_client(project, url, token_env))
    for p in _run(lambda: source.list_pipelines(ref=ref, status=status, limit=limit)):
        typer.echo(
            f"{p.id:<8} {p.state.value:<9} {p.ref:<20} {p.sha[:8]} "
            f"{_seconds(p.duration_seconds)}"
        )


@gitlab_app.command("pipeline")
def pipeline_command(
    pipeline_id: Annotated[int, typer.Argument(help="Pipeline id.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Show a pipeline and its jobs. Success needs the server to report it."""
    source = GitLabPipelines(_client(project, url, token_env))
    pipeline = _run(lambda: source.get_pipeline(pipeline_id))
    jobs = _run(lambda: source.list_jobs(pipeline_id))
    typer.echo(
        f"Pipeline {pipeline.id}: {pipeline.state.value} "
        f"(server status {pipeline.raw_status!r}) on {pipeline.ref} {pipeline.sha[:8]}"
    )
    for job in jobs:
        extra = f"  {job.failure_reason}" if job.failure_reason else ""
        typer.echo(
            f"  [{job.stage}] {job.name:<24} {job.state.value:<9} "
            f"{_seconds(job.duration_seconds)}  job {job.id}{extra}"
        )


@gitlab_app.command("log")
def log_command(
    job_id: Annotated[int, typer.Argument(help="Job id.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
    tail: Annotated[int, typer.Option(help="Characters to keep from the end.")] = 5000,
) -> None:
    """Show the end of a job log, with secrets masked and marked as untrusted."""
    source = GitLabPipelines(_client(project, url, token_env))
    log = _run(lambda: source.job_log(job_id, max_chars=tail))
    typer.echo(fence(redact_secrets(log), source=f"GitLab job {job_id} log"))


@gitlab_app.command("artifacts")
def artifacts_command(
    job_id: Annotated[int, typer.Argument(help="Job id.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """List the artifacts a job declares."""
    source = GitLabPipelines(_client(project, url, token_env))
    files = _run(lambda: source.list_artifacts(job_id))
    for artifact in files:
        typer.echo(f"{artifact.filename}  {artifact.size} bytes  {artifact.kind}")
    if not files:
        typer.echo("This job has no artifacts.")


@gitlab_app.command("artifact")
def artifact_command(
    job_id: Annotated[int, typer.Argument(help="Job id.")],
    path: Annotated[str, typer.Argument(help="File inside the artifacts.")],
    project: ProjectOption,
    out: Annotated[Path, typer.Option("--out", help="Where to save it.")],
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Download one artifact file."""
    source = GitLabPipelines(_client(project, url, token_env))
    try:
        data = _run(lambda: source.download_artifact(job_id, path))
    except ValueError as error:
        _fail(str(error))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    typer.echo(f"Saved {len(data)} bytes to {out}")
