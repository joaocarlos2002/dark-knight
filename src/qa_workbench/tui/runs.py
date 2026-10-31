"""Start runs from the TUI with the same services and safeguards as the CLI.

Each function raises :class:`RunFailed` with a message a person can act on (the
guard's refusals, a missing authorization, a bad definition) instead of exiting,
and is meant to run in a worker thread. Nothing here has logic of its own: the
API runner, the security checks, and the release analysis are the ones the
commands call, behind the same action guard and audit log.
"""

from dataclasses import dataclass
from pathlib import Path

from qa_workbench.api import cli as api_cli
from qa_workbench.api.definition import load_definition
from qa_workbench.api.errors import ApiError
from qa_workbench.api.guarded import GuardedTransport
from qa_workbench.api.records import save_flow
from qa_workbench.api.runner import ApiRunner
from qa_workbench.core.config import ConfigurationError
from qa_workbench.integrations.errors import IntegrationError
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.gitlab.connect import open_client
from qa_workbench.integrations.gitlab.repository import GitLabRepository
from qa_workbench.projects.errors import ProjectError
from qa_workbench.release.analysis import analyze_release
from qa_workbench.release.records import save_analysis
from qa_workbench.sectest import authorization as auth
from qa_workbench.sectest.checks import CHECKS
from qa_workbench.sectest.records import UnsafeToSaveError, save_run
from qa_workbench.sectest.runner import run_checks
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository

KNOWN_CHECKS = frozenset(CHECKS)
_ERRORS = (
    ApiError,
    auth.NotAuthorized,
    SecurityError,
    AuditError,
    SecuritySettingsError,
    UnsafeToSaveError,
    IntegrationError,
    ConfigurationError,
    ProjectError,
    StorageError,
    ValueError,
    OSError,
)


class RunFailed(Exception):
    """A run could not start or finish; the message says why."""


@dataclass(frozen=True)
class RunOutcome:
    record_id: str
    ok: bool
    summary: str


def _guard(repository: MarkdownRepository) -> ActionGuard:
    return ActionGuard(load_settings(repository.root), AuditLog(repository.root))


def run_api_definition(repository: MarkdownRepository, definition: Path) -> RunOutcome:
    """Run an API test definition and save the sanitized result."""
    try:
        loaded = load_definition(definition)
        transport = GuardedTransport(api_cli.default_transport(), _guard(repository))
        flow = ApiRunner(transport).run(loaded)
        record = save_flow(repository, flow)
    except _ERRORS as error:
        raise RunFailed(str(error)) from error
    failed = [s for s in flow.steps if s.status != "passed"]
    detail = f", {len(failed)} step(s) failed" if failed else ""
    return RunOutcome(
        record.id,
        flow.status == "passed",
        f"{flow.status.upper()}: {len(flow.steps)} step(s){detail}. "
        f"Saved as {record.id}.",
    )


def run_release_analysis(
    repository: MarkdownRepository,
    project_id: str,
    data_dir: Path,
    *,
    ref: str | None = None,
    since: str | None = None,
    limit: int = 30,
) -> RunOutcome:
    """Read the project's commits and merge requests and save the analysis."""
    try:
        client = open_client(
            project_id, gitlab_cli.default_gateway(), data_dir=data_dir
        )
        _guard(repository).authorize(
            ActionRequest(
                "read repository history",
                Category.READ,
                f"commits since {since or '-'} on {ref or 'default branch'}",
                target_url=client.base_url,
                requested_by="release-analysis",
            )
        )
        analysis = analyze_release(
            GitLabRepository(client), repository, ref=ref, since=since, limit=limit
        )
        record = save_analysis(repository, analysis)
    except _ERRORS as error:
        raise RunFailed(str(error)) from error
    return RunOutcome(
        record.id,
        True,
        f"{record.id}: risk {analysis.risk_level}. {analysis.regression}",
    )


def authorization_text(repository: MarkdownRepository) -> str:
    """What the security checks may do right now (always visible on the page)."""
    try:
        current = auth.load(repository.root)
    except auth.NotAuthorized as error:
        return f"Security-test authorization is unreadable: {error}"
    if current is None:
        return "No security-test authorization: nothing can run (U grants one)."
    from datetime import UTC, datetime

    state = "EXPIRED" if current.expired(datetime.now(UTC)) else "valid"
    return (
        f"Security tests: {state}, by {current.authorized_by}, "
        f"{', '.join(current.hosts)}, until "
        f"{current.expires_at.isoformat(timespec='minutes')}"
    )


def grant_authorization(
    repository: MarkdownRepository,
    *,
    by: str,
    purpose: str,
    host: str,
    days: float,
) -> str:
    try:
        granted = auth.grant(
            repository.root,
            authorized_by=by,
            purpose=purpose,
            hosts=(host,),
            checks=tuple(CHECKS),
            known_checks=KNOWN_CHECKS,
            days=days,
        )
    except _ERRORS as error:
        raise RunFailed(str(error)) from error
    return f"Authorized until {granted.expires_at.isoformat(timespec='minutes')}."


def revoke_authorization(repository: MarkdownRepository, *, by: str) -> str:
    try:
        done = auth.revoke(repository.root, by=by)
    except _ERRORS as error:
        raise RunFailed(str(error)) from error
    return "Authorization revoked." if done else "There was no authorization."


def run_security_checks(
    repository: MarkdownRepository,
    url: str,
    *,
    protected_paths: tuple[str, ...] = (),
) -> RunOutcome:
    """Run the authorized, passive checks against ``url`` and save the result."""
    from qa_workbench.sectest.cli import default_gateway

    try:
        run = run_checks(
            url=url,
            checks=tuple(CHECKS),
            gateway=default_gateway(),
            authorization=auth.load(repository.root),
            guard=_guard(repository),
            protected_paths=protected_paths,
        )
        record = save_run(repository, run)
    except _ERRORS as error:
        raise RunFailed(str(error)) from error
    confirmed = [f for f in run.findings if f.confirmed]
    return RunOutcome(
        record.id,
        run.ok,
        f"{record.id}: {len(confirmed)} confirmed, "
        f"{len(run.findings) - len(confirmed)} hypotheses.",
    )
