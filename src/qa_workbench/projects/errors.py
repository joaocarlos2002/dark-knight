"""Errors raised by project operations."""

from pathlib import Path


class ProjectError(Exception):
    """Base class for project failures."""


class ProjectNotFoundError(ProjectError):
    """Raised when a project id does not exist."""

    def __init__(self, project_id: str) -> None:
        super().__init__(f"Project {project_id} was not found.")
        self.project_id = project_id


class InvalidProjectError(ProjectError):
    """Raised when a project record cannot be read or fails validation."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"Invalid project record {path}: {reason}")
        self.path = path
        self.reason = reason


class ProjectStateError(ProjectError):
    """Raised when an operation is not allowed in the project's current state."""
