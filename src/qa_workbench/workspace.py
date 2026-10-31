"""The record kinds of a project and how to open its repository."""

from pathlib import Path

from qa_workbench.api.records import API_SCHEMA
from qa_workbench.bughunt.schema import BUG_SCHEMA
from qa_workbench.core.config import AppConfig
from qa_workbench.executions.schema import EXECUTION_SCHEMA
from qa_workbench.plans.schema import REVIEW_POLICY as PLAN_REVIEW
from qa_workbench.plans.schema import TEST_PLAN_SCHEMA
from qa_workbench.projects.errors import ProjectStateError
from qa_workbench.projects.models import Project
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.publishing.schema import COMMENT_SCHEMA
from qa_workbench.release.records import RELEASE_SCHEMA
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.requirements.schema import REVIEW_POLICY as REQUIREMENT_REVIEW
from qa_workbench.review.policy import ReviewPolicy
from qa_workbench.sectest.records import SEC_SCHEMA
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema
from qa_workbench.suites.schema import SUITE_SCHEMA
from qa_workbench.testcases.schema import REVIEW_POLICY as TEST_CASE_REVIEW
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


def all_schemas() -> list[RecordSchema]:
    """Every record schema the workbench knows. New record kinds are added here."""
    return [
        EVIDENCE_SCHEMA,
        REQUIREMENT_SCHEMA,
        TEST_CASE_SCHEMA,
        SUITE_SCHEMA,
        TEST_PLAN_SCHEMA,
        EXECUTION_SCHEMA,
        API_SCHEMA,
        BUG_SCHEMA,
        RELEASE_SCHEMA,
        SEC_SCHEMA,
        COMMENT_SCHEMA,
    ]


def review_policies() -> dict[str, ReviewPolicy]:
    """The record kinds that go through human review, by prefix."""
    return {"REQ": REQUIREMENT_REVIEW, "TC": TEST_CASE_REVIEW, "TP": PLAN_REVIEW}


def open_repository(project_id: str, *, writable: bool = True) -> MarkdownRepository:
    """Open the record repository of an existing project.

    Raises ``ProjectNotFoundError`` for an unknown project, and
    ``ProjectStateError`` when writing to an archived one.
    """
    config = AppConfig.load()
    project = ProjectRepository(config.data_dir).open(project_id)
    if writable and project.archived:
        raise ProjectStateError(
            f"Project {project.id} is archived and cannot be changed."
        )
    return repository_for(config.data_dir, project)


def repository_for(data_dir: Path, project: Project) -> MarkdownRepository:
    """The record repository of an already opened project."""
    root = ProjectRepository(data_dir).root
    return MarkdownRepository(root / project.id, all_schemas())
