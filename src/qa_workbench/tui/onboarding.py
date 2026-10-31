"""First run: welcome the person and walk them through creating a project.

Shown only when the workbench opens with no project and none exists yet. It
reuses the ordinary dialogs, so nothing here is a new screen. Reading from the
project's repository host is a security decision, so it is asked about
explicitly and never granted silently.
"""

import getpass
from typing import Any
from urllib.parse import urlsplit

from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.models import Project
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import LOOPBACK_HOSTS
from qa_workbench.security.settings import (
    SecuritySettings,
    SecuritySettingsError,
    load_settings,
    save_settings,
)
from qa_workbench.tui import identity
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.workspace import repository_for

WELCOME_TITLE = f"{identity.COMPANY} / {identity.PRODUCT}"
WELCOME_MESSAGE = (
    "Welcome. This workbench keeps your quality evidence in one place: "
    "requirements, test cases, executions, and what proves each result.\n\n"
    "Everything starts with a project, usually one repository. "
    "Create yours now?"
)
FIELDS = (
    FormField("name", "Project name", "Checkout service", required=True),
    FormField(
        "repository",
        "Repository URL (GitLab)",
        "https://gitlab.example.com/group/app",
    ),
)


def needs_welcome(projects: ProjectRepository) -> bool:
    """A brand-new workbench: no project is open and none has been created."""
    return not projects.list_projects(include_archived=True).projects


def repository_host(url: str) -> str:
    """The host to read from, or ``""`` when the URL has none worth allowing."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host in LOOPBACK_HOSTS:
        return ""
    return host


def validate_repository(values: dict[str, str]) -> str | None:
    url = values["repository"]
    if url:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return "Use a URL like https://gitlab.example.com/group/app."
    return None


def start(app: Any) -> None:
    """Open the welcome. ``app`` is the running ``WorkbenchApp``."""

    def welcomed(go: bool | None) -> None:
        if go:
            _ask_project(app)

    app.push_screen(
        ConfirmationDialog(
            WELCOME_TITLE, WELCOME_MESSAGE, confirm_label="Create project"
        ),
        welcomed,
    )


def _ask_project(app: Any) -> None:
    created: list[Project] = []

    def commit(values: dict[str, str]) -> str | None:
        try:
            created.append(
                ProjectRepository(app._data_dir).create(
                    values["name"], repository=values["repository"]
                )
            )
        except ProjectError as error:
            return str(error)
        return None

    def done(values: dict[str, str] | None) -> None:
        if values is None or not created:
            return
        project = created[0]
        app.open_project(project.id)
        _offer_host(app, project)

    app.push_screen(
        FormDialog(
            "New project",
            FIELDS,
            submit_label="Create",
            validate=validate_repository,
            commit=commit,
        ),
        done,
    )


def _offer_host(app: Any, project: Project) -> None:
    host = repository_host(project.repository)
    if not host:
        return

    def decided(allow: bool | None) -> None:
        if allow:
            _allow(app, project, host)
        else:
            app.notify(
                f"Reads from {host} stay blocked. Allow it later with "
                f"`batman security set -p {project.id} --allow-host {host} --by NAME`.",
                title="Host not allowed",
            )

    app.push_screen(
        ConfirmationDialog(
            "Allow reading from this server?",
            f"The workbench only talks to servers you allow.\n\n"
            f"Allow it to read issues, merge requests, and pipelines from {host}? "
            "It sends your GitLab token there, read-only, and every request is "
            "written to the audit log.",
            confirm_label=f"Allow {host}",
        ),
        decided,
    )


def _allow(app: Any, project: Project, host: str) -> None:
    root = repository_for(app._data_dir, project).root
    try:
        current = load_settings(root)
        if host not in current.allowed_hosts:
            updated = SecuritySettings(
                mode=current.mode,
                authorized_environments=current.authorized_environments,
                allowed_hosts=(*current.allowed_hosts, host),
                max_requests_per_minute=current.max_requests_per_minute,
                timeout_seconds=current.timeout_seconds,
                max_retries=current.max_retries,
                data_policy=current.data_policy,
            )
            save_settings(root, updated)
            AuditLog(root).append(
                "settings_changed",
                getpass.getuser(),
                {
                    "mode": updated.mode.value,
                    "allowed_hosts": list(updated.allowed_hosts),
                },
            )
    except (SecuritySettingsError, AuditError, OSError) as error:
        app.notify(str(error), severity="error", title="Host not allowed")
        return
    app.notify(f"{host} is allowed for {project.id}.", title="Security")
