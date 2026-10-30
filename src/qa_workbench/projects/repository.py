"""Filesystem persistence for projects.

Layout, per the product specification::

    <data_dir>/projects/<PROJ-NNN>/project.yaml
    <data_dir>/projects/<PROJ-NNN>/README.md
"""

import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from qa_workbench.projects.errors import (
    InvalidProjectError,
    ProjectNotFoundError,
    ProjectStateError,
)
from qa_workbench.projects.models import (
    PROJECT_ID_PATTERN,
    PROJECT_ID_PREFIX,
    Environment,
    Project,
    ProjectStatus,
)

PROJECT_FILE = "project.yaml"
README_FILE = "README.md"

_ID_NUMBER = re.compile(rf"^{PROJECT_ID_PREFIX}-(\d+)$")


@dataclass(frozen=True)
class ProjectListing:
    """Result of listing projects.

    Records that cannot be read are reported in ``errors`` instead of being
    dropped, so a corrupt project is never mistaken for a missing one.
    """

    projects: tuple[Project, ...]
    errors: tuple[InvalidProjectError, ...]


def _now() -> datetime:
    return datetime.now().astimezone()


def _write_atomic(path: Path, text: str) -> None:
    """Write a file so readers never observe a partial update."""
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _readme(project: Project) -> str:
    lines = [f"# {project.id} — {project.name}", ""]
    if project.description:
        lines += [project.description, ""]
    lines += [
        "Project settings live in [project.yaml](project.yaml).",
        "Do not store tokens or passwords in this folder.",
        "",
    ]
    return "\n".join(lines)


class ProjectRepository:
    """Create, list, open, and archive projects under a data directory."""

    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "projects"

    def create(
        self,
        name: str,
        *,
        description: str = "",
        repository: str = "",
        directory: str = "",
        environments: list[Environment] | None = None,
        frameworks: list[str] | None = None,
        languages: list[str] | None = None,
        commands: dict[str, str] | None = None,
    ) -> Project:
        """Create a new active project with the next free id."""
        self.root.mkdir(parents=True, exist_ok=True)
        timestamp = _now()
        try:
            project = Project(
                id=self._next_id(),
                name=name,
                description=description,
                repository=repository,
                directory=directory,
                environments=environments or [],
                frameworks=frameworks or [],
                languages=languages or [],
                commands=commands or {},
                created_at=timestamp,
                updated_at=timestamp,
            )
        except ValidationError as error:
            raise InvalidProjectError(self.root, _describe(error)) from error

        folder = self.root / project.id
        folder.mkdir(exist_ok=False)
        self._save(project)
        _write_atomic(folder / README_FILE, _readme(project))
        return project

    def list_projects(self, *, include_archived: bool = False) -> ProjectListing:
        """List projects ordered by id."""
        projects: list[Project] = []
        errors: list[InvalidProjectError] = []
        if self.root.is_dir():
            for folder in sorted(self.root.iterdir()):
                if not folder.is_dir() or not _ID_NUMBER.match(folder.name):
                    continue
                try:
                    project = self.open(folder.name)
                except InvalidProjectError as error:
                    errors.append(error)
                    continue
                if include_archived or not project.archived:
                    projects.append(project)
        return ProjectListing(tuple(projects), tuple(errors))

    def open(self, project_id: str) -> Project:
        """Load and validate a project."""
        if not re.match(PROJECT_ID_PATTERN, project_id):
            raise ProjectNotFoundError(project_id)
        path = self.root / project_id / PROJECT_FILE
        if not path.is_file():
            raise ProjectNotFoundError(project_id)
        try:
            document: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
            raise InvalidProjectError(path, f"cannot be read: {error}") from error
        if not isinstance(document, dict):
            raise InvalidProjectError(path, "must contain a mapping of fields")
        try:
            project = Project.model_validate(document)
        except ValidationError as error:
            raise InvalidProjectError(path, _describe(error)) from error
        if project.id != project_id:
            raise InvalidProjectError(
                path, f"id {project.id} does not match its folder {project_id}"
            )
        return project

    def archive(self, project_id: str) -> Project:
        """Archive a project. Its files are kept; nothing is deleted."""
        project = self.open(project_id)
        if project.archived:
            raise ProjectStateError(f"Project {project_id} is already archived.")
        project.status = ProjectStatus.ARCHIVED
        project.updated_at = _now()
        self._save(project)
        return project

    def _next_id(self) -> str:
        numbers = [
            int(match.group(1))
            for entry in self.root.iterdir()
            if (match := _ID_NUMBER.match(entry.name))
        ]
        return f"{PROJECT_ID_PREFIX}-{max(numbers, default=0) + 1:03d}"

    def _save(self, project: Project) -> None:
        document = project.model_dump(mode="json")
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        _write_atomic(self.root / project.id / PROJECT_FILE, text)


def _describe(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'record'}: {item['msg']}"
        for item in error.errors()
    )
