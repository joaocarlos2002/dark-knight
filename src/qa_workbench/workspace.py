"""The record kinds of a project and how to open its repository."""

from qa_workbench.core.config import AppConfig
from qa_workbench.projects.errors import ProjectStateError
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema


def all_schemas() -> list[RecordSchema]:
    """Every record schema the workbench knows. New record kinds are added here."""
    return [EVIDENCE_SCHEMA, REQUIREMENT_SCHEMA]


def open_repository(project_id: str, *, writable: bool = True) -> MarkdownRepository:
    """Open the record repository of an existing project.

    Raises ``ProjectNotFoundError`` for an unknown project, and
    ``ProjectStateError`` when writing to an archived one.
    """
    config = AppConfig.load()
    projects = ProjectRepository(config.data_dir)
    project = projects.open(project_id)
    if writable and project.archived:
        raise ProjectStateError(
            f"Project {project.id} is archived and cannot be changed."
        )
    return MarkdownRepository(projects.root / project.id, all_schemas())
