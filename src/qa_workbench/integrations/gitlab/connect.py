"""Opening a project's GitLab client behind the action guard.

Shared by the CLI and the TUI. It raises errors instead of exiting, so each
caller reports them its own way.
"""

from pathlib import Path

from qa_workbench.core.config import AppConfig
from qa_workbench.integrations.errors import NotConfiguredError
from qa_workbench.integrations.gitlab.client import (
    DEFAULT_TOKEN_ENV,
    SYSTEM,
    GitLabClient,
    GitLabConnection,
)
from qa_workbench.integrations.gitlab.wiki import GitLabWiki, group_of
from qa_workbench.integrations.guarded import GuardedGateway
from qa_workbench.integrations.http import HttpGateway
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.settings import load_settings
from qa_workbench.workspace import repository_for


def open_client(
    project_id: str,
    gateway: HttpGateway,
    *,
    url: str | None = None,
    token_env: str = DEFAULT_TOKEN_ENV,
    data_dir: Path | None = None,
) -> GitLabClient:
    """The GitLab client of a project: every request goes through the guard.

    Raises ``ProjectError``, ``IntegrationError``, ``AuditError``,
    ``SecuritySettingsError``, or ``ConfigurationError``.
    """
    data = data_dir or AppConfig.load().data_dir
    opened = ProjectRepository(data).open(project_id)
    source = url or opened.repository
    if not source:
        raise NotConfiguredError(
            SYSTEM,
            f"{project_id} has no repository URL",
            hint="Pass --url https://gitlab.example.com/group/app",
        )
    connection = GitLabConnection.from_repository_url(source, token_env=token_env)
    root = repository_for(data, opened).root
    guard = ActionGuard(load_settings(root), AuditLog(root))
    return GitLabClient(connection, GuardedGateway(gateway, guard, SYSTEM))


def open_wiki(client: GitLabClient, group: str | None) -> tuple[GitLabWiki, str]:
    """The group wiki that goes with a client, and the group it reads."""
    chosen = (group or group_of(client.project_name)).strip()
    if not chosen:
        raise NotConfiguredError(
            SYSTEM,
            "the project is not inside a group",
            hint="Pass the group id or path",
        )
    return GitLabWiki(client, chosen), chosen


def open_writer(
    project_id: str,
    gateway: HttpGateway,
    *,
    url: str | None = None,
    token_env: str = DEFAULT_TOKEN_ENV,
    data_dir: Path | None = None,
) -> tuple[GitLabClient, ActionGuard]:
    """A client that may write, and the guard that must approve each write.

    The client has no guard of its own: the caller asks ``guard.authorize`` for
    the exact action first, which checks the host and needs a person's approval.
    """
    data = data_dir or AppConfig.load().data_dir
    opened = ProjectRepository(data).open(project_id)
    source = url or opened.repository
    if not source:
        raise NotConfiguredError(
            SYSTEM,
            f"{project_id} has no repository URL",
            hint="Pass --url https://gitlab.example.com/group/app",
        )
    connection = GitLabConnection.from_repository_url(source, token_env=token_env)
    root = repository_for(data, opened).root
    guard = ActionGuard(load_settings(root), AuditLog(root))
    return GitLabClient(connection, gateway), guard
