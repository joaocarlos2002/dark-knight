"""``batman security`` commands: settings, approvals, and the audit log."""

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ApprovalBook, ApprovalError
from qa_workbench.security.policy import AutonomyMode
from qa_workbench.security.settings import (
    SecuritySettings,
    SecuritySettingsError,
    load_settings,
    save_settings,
)
from qa_workbench.workspace import open_repository

security_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Autonomy mode, authorized scope, approvals, and the audit log.",
)

ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id, such as PROJ-001.")
]


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _root(project: str, *, writable: bool) -> Path:
    try:
        return open_repository(project, writable=writable).root
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))


@security_app.command("show")
def show_command(project: ProjectOption) -> None:
    """Show the project's security settings."""
    try:
        settings = load_settings(_root(project, writable=False))
    except SecuritySettingsError as error:
        _fail(str(error))
    typer.echo(f"mode: {settings.mode.value}")
    typer.echo(
        f"authorized environments: {', '.join(settings.authorized_environments) or '-'}"
    )
    typer.echo(
        "allowed hosts: "
        + (
            ", ".join(settings.allowed_hosts)
            or "- (every external host needs approval)"
        )
    )
    typer.echo(f"max requests per minute: {settings.max_requests_per_minute}")
    typer.echo(
        f"timeout: {settings.timeout_seconds:g}s   retries: {settings.max_retries}"
    )
    typer.echo(f"data policy: {settings.data_policy}")


@security_app.command("set")
def set_command(
    project: ProjectOption,
    mode: Annotated[
        str | None,
        typer.Option(help="assisted, semi_autonomous, controlled_autonomous."),
    ] = None,
    allow_host: Annotated[
        list[str] | None, typer.Option(help="Add an allowed host. Repeatable.")
    ] = None,
    remove_host: Annotated[
        list[str] | None, typer.Option(help="Remove an allowed host.")
    ] = None,
    environment: Annotated[
        list[str] | None, typer.Option(help="Add an authorized environment.")
    ] = None,
    rate: Annotated[int | None, typer.Option(help="Requests per minute.")] = None,
    timeout: Annotated[float | None, typer.Option(help="Seconds.")] = None,
    retries: Annotated[int | None, typer.Option(help="Retry attempts.")] = None,
    by: Annotated[str, typer.Option(help="Who is changing the settings.")] = "",
) -> None:
    """Change settings. Changing security settings is itself audited."""
    root = _root(project, writable=True)
    if not by.strip():
        _fail("Say who is changing the settings with --by NAME.")
    try:
        current = load_settings(root)
        new_mode = AutonomyMode(mode) if mode else current.mode
        hosts = [h for h in current.allowed_hosts if h not in (remove_host or [])]
        hosts += [h for h in (allow_host or []) if h not in hosts]
        environments = list(current.authorized_environments)
        environments += [e for e in (environment or []) if e not in environments]
        updated = SecuritySettings(
            mode=new_mode,
            authorized_environments=tuple(environments),
            allowed_hosts=tuple(hosts),
            max_requests_per_minute=rate or current.max_requests_per_minute,
            timeout_seconds=timeout or current.timeout_seconds,
            max_retries=current.max_retries if retries is None else retries,
            data_policy=current.data_policy,
        )
        save_settings(root, updated)
        AuditLog(root).append(
            "settings_changed",
            by.strip(),
            {"mode": updated.mode.value, "allowed_hosts": list(updated.allowed_hosts)},
        )
    except ValueError as error:
        _fail(str(error))
    except AuditError as error:
        _fail(str(error))
    typer.echo("Settings saved.")


@security_app.command("approvals")
def approvals_command(
    project: ProjectOption,
    all_: Annotated[
        bool, typer.Option("--all", help="Include decided requests.")
    ] = False,
) -> None:
    """List approval requests (pending ones by default)."""
    try:
        book = ApprovalBook(AuditLog(_root(project, writable=False)))
        found = book.all() if all_ else book.pending()
    except AuditError as error:
        _fail(str(error))
    for approval in found:
        typer.echo(
            f"{approval.request_id}  {approval.status:<8} {approval.category:<18} "
            f"{approval.action}  (by {approval.requested_by})"
        )
        if approval.detail:
            typer.echo(f"           {approval.detail}")
    if not found:
        typer.echo("No approval requests.")


def _decide(project: str, request_id: str, approve: bool, by: str, reason: str) -> None:
    root = _root(project, writable=True)
    try:
        ApprovalBook(AuditLog(root)).decide(
            request_id, approve=approve, by=by, reason=reason
        )
    except (ApprovalError, AuditError) as error:
        _fail(str(error))
    typer.echo(f"{request_id} {'approved' if approve else 'denied'} by {by}.")


@security_app.command("approve")
def approve_command(
    request_id: Annotated[
        str, typer.Argument(help="Request id, such as APR-1a2b3c4d.")
    ],
    project: ProjectOption,
    by: Annotated[str, typer.Option(help="Your name.")],
    reason: Annotated[str, typer.Option(help="Why (optional).")] = "",
) -> None:
    """Approve one request. It is single-use and expires after an hour."""
    _decide(project, request_id, True, by, reason)


@security_app.command("deny")
def deny_command(
    request_id: Annotated[str, typer.Argument(help="Request id.")],
    project: ProjectOption,
    by: Annotated[str, typer.Option(help="Your name.")],
    reason: Annotated[str, typer.Option(help="Why (required).")],
) -> None:
    """Deny one request."""
    _decide(project, request_id, False, by, reason)


@security_app.command("audit")
def audit_command(
    project: ProjectOption,
    verify: Annotated[
        bool, typer.Option("--verify", help="Only check the hash chain.")
    ] = False,
    limit: Annotated[int, typer.Option(help="Most recent entries to show.")] = 20,
) -> None:
    """Show the audit log, or verify that it was not altered."""
    log = AuditLog(_root(project, writable=False))
    try:
        entries = log.entries()
    except AuditError as error:
        _fail(str(error))
    if verify:
        typer.echo(f"Audit log intact: {len(entries)} entries.")
        return
    for entry in entries[-limit:]:
        typer.echo(
            f"{entry.sequence:>4} {entry.time}  {entry.kind:<18} "
            f"{entry.actor}  {entry.data}"
        )
    if not entries:
        typer.echo("The audit log is empty.")
