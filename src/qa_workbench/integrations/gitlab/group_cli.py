"""``batman gitlab board`` and ``issue-links``: the group's boards and issue links."""

from typing import Annotated

import typer

from qa_workbench.integrations.gitlab.board import GitLabBoard, GitLabIssueLinks
from qa_workbench.integrations.gitlab.cli import (
    DEFAULT_TOKEN_ENV,
    LimitOption,
    ProjectOption,
    TokenEnvOption,
    UrlOption,
    _fail,
    _run,
    client_for,
    gitlab_app,
)
from qa_workbench.integrations.gitlab.wiki import group_of


@gitlab_app.command("board")
def board_command(
    project: ProjectOption,
    labels: Annotated[
        str,
        typer.Option(
            "--labels",
            help="Board filter label and column label, comma separated, such as "
            "team::dev,workflow::QA (both are required).",
        ),
    ] = "",
    group: Annotated[
        str | None,
        typer.Option("--group", help="Group id or path. Defaults to the project's."),
    ] = None,
    only: Annotated[
        str, typer.Option("--only", help="Only issues of this project path.")
    ] = "",
    state: Annotated[str, typer.Option(help="opened, closed, or all.")] = "opened",
    include_test_cases: Annotated[
        bool, typer.Option("--include-test-cases", help="Also list test cases.")
    ] = False,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
    limit: LimitOption = 100,
) -> None:
    """Read a board column across the whole group. Test cases are left out."""
    client = client_for(project, url, token_env)
    chosen = group or group_of(client.project_name)
    if not chosen:
        _fail("The project is not inside a group. Pass --group.")
    wanted = tuple(label.strip() for label in labels.split(",") if label.strip())
    issues = _run(
        lambda: GitLabBoard(client, chosen).column(
            wanted,
            state=state,
            project=only,
            include_test_cases=include_test_cases,
            limit=limit,
        )
    )
    for issue in issues:
        who = ",".join(issue.assignees) or "-"
        typer.echo(
            f"{issue.reference:<48} {issue.state:<7} {issue.title}  "
            f"[{', '.join(issue.labels) or '-'}]  @{who}"
        )
    if not issues:
        typer.echo("No issues match.")


@gitlab_app.command("issue-links")
def issue_links_command(
    iid: Annotated[int, typer.Argument(help="Issue number.")],
    project: ProjectOption,
    url: UrlOption = None,
    token_env: TokenEnvOption = DEFAULT_TOKEN_ENV,
) -> None:
    """Related issues, related merge requests, and the merge requests that close it.
    Use --url to read an issue of another project."""
    links = _run(
        lambda: GitLabIssueLinks(client_for(project, url, token_env)).links(iid)
    )
    for link in links:
        typer.echo(f"{link.kind:<22} {link.reference:<40} {link.state:<7} {link.title}")
    if not links:
        typer.echo("This issue has no links.")
