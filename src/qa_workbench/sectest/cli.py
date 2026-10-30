"""``batman security-tests`` commands."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.projects.errors import ProjectError
from qa_workbench.sectest import authorization as auth
from qa_workbench.sectest.checks import CHECKS
from qa_workbench.sectest.records import UnsafeToSaveError, save_run
from qa_workbench.sectest.runner import run_checks
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.workspace import open_repository

security_tests_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Authorized, scoped, rate-limited passive security checks.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]
KNOWN = frozenset(CHECKS)


def default_gateway():
    """The real HTTP client. Tests replace this so nothing touches the network."""
    return gitlab_cli.default_gateway()


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


@security_tests_app.command("authorize")
def authorize_command(
    project: ProjectOption,
    by: Annotated[str, typer.Option(help="Who authorizes the tests.")],
    purpose: Annotated[str, typer.Option(help="What the tests are for.")],
    host: Annotated[list[str], typer.Option(help="Exact host. Repeatable.")],
    check: Annotated[
        list[str] | None,
        typer.Option(help=f"Check to allow. Default: all ({', '.join(CHECKS)})."),
    ] = None,
    days: Annotated[float, typer.Option(help="Validity in days (max 30).")] = 1,
) -> None:
    """Grant a scoped, expiring authorization. Audited."""
    try:
        root = open_repository(project, writable=True).root
        granted = auth.grant(
            root,
            authorized_by=by,
            purpose=purpose,
            hosts=tuple(host),
            checks=tuple(check or CHECKS),
            known_checks=KNOWN,
            days=days,
        )
    except (auth.NotAuthorized, AuditError, ConfigurationError, ProjectError) as error:
        _fail(str(error))
    typer.echo(
        f"Authorized by {granted.authorized_by} until "
        f"{granted.expires_at.isoformat(timespec='minutes')}: "
        f"{', '.join(granted.hosts)} ({', '.join(granted.checks)})."
    )


@security_tests_app.command("revoke")
def revoke_command(
    project: ProjectOption, by: Annotated[str, typer.Option(help="Who revokes.")]
) -> None:
    """Remove the authorization."""
    try:
        done = auth.revoke(open_repository(project, writable=True).root, by=by)
    except (auth.NotAuthorized, AuditError, ConfigurationError, ProjectError) as error:
        _fail(str(error))
    typer.echo("Authorization revoked." if done else "There was no authorization.")


@security_tests_app.command("status")
def status_command(project: ProjectOption) -> None:
    """Show the current authorization."""
    try:
        current = auth.load(open_repository(project, writable=False).root)
    except (auth.NotAuthorized, ConfigurationError, ProjectError) as error:
        _fail(str(error))
    if current is None:
        typer.echo("No security-test authorization. Nothing can run.")
        return
    from datetime import UTC, datetime

    state = "EXPIRED" if current.expired(datetime.now(UTC)) else "valid"
    typer.echo(f"{state}: by {current.authorized_by} - {current.purpose}")
    typer.echo(f"hosts: {', '.join(current.hosts)}")
    typer.echo(f"checks: {', '.join(current.checks)}")
    typer.echo(f"expires: {current.expires_at.isoformat(timespec='minutes')}")


@security_tests_app.command("run")
def run_command(
    url: Annotated[str, typer.Argument(help="Target URL.")],
    project: ProjectOption,
    check: Annotated[
        list[str] | None, typer.Option(help="Check to run. Default: all.")
    ] = None,
    protected_path: Annotated[
        list[str] | None,
        typer.Option(help="A path that requires login (for unauthenticated-access)."),
    ] = None,
) -> None:
    """Run the authorized checks and save the sanitized result."""
    try:
        repository = open_repository(project, writable=True)
        settings = load_settings(repository.root)
        guard = ActionGuard(settings, AuditLog(repository.root))
        run = run_checks(
            url=url,
            checks=tuple(check or CHECKS),
            gateway=default_gateway(),
            authorization=auth.load(repository.root),
            guard=guard,
            protected_paths=tuple(protected_path or ()),
        )
        record = save_run(repository, run)
    except (
        auth.NotAuthorized,
        SecurityError,
        AuditError,
        SecuritySettingsError,
        UnsafeToSaveError,
        ConfigurationError,
        ProjectError,
        StorageError,
    ) as error:
        _fail(str(error))
    confirmed = [f for f in run.findings if f.confirmed]
    typer.echo(
        f"Saved {record.id}: {len(confirmed)} confirmed, "
        f"{len(run.findings) - len(confirmed)} hypotheses."
    )
    for finding in run.findings:
        kind = "CONFIRMED " if finding.confirmed else "HYPOTHESIS"
        typer.echo(f"  {kind} {finding.severity:<6} {finding.title}")
    for item in run.checks:
        if item.status == "error":
            typer.echo(f"  ERROR      {item.check}: {item.error}")
    if not run.ok:
        raise typer.Exit(1)


@security_tests_app.command("list")
def list_command(project: ProjectOption) -> None:
    """List saved runs."""
    try:
        listing = open_repository(project, writable=False).list_records("SEC")
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    for record in listing.records:
        meta = record.metadata
        typer.echo(
            f"{record.id}  {meta['status']:<10} {meta['confirmed']} confirmed, "
            f"{meta['hypotheses']} hypotheses  {meta['target']}"
        )
    for problem in listing.errors:
        typer.echo(f"Damaged record: {problem}", err=True)
    if not listing.records and not listing.errors:
        typer.echo("No security runs yet.")


@security_tests_app.command("show")
def show_command(
    record_id: Annotated[str, typer.Argument(help="SEC id.")], project: ProjectOption
) -> None:
    """Show a saved run."""
    try:
        record = open_repository(project, writable=False).get(record_id)
    except (ConfigurationError, ProjectError, StorageError) as error:
        _fail(str(error))
    typer.echo(record.body)
