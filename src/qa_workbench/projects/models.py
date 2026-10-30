"""Project domain model (REQ-002, REQ-003)."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

PROJECT_ID_PREFIX = "PROJ"
PROJECT_ID_PATTERN = rf"^{PROJECT_ID_PREFIX}-\d{{3,}}$"

NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ProjectStatus(Enum):
    """Lifecycle state of a project."""

    ACTIVE = "active"
    ARCHIVED = "archived"


def _check_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"must be an http(s) URL with a host, got {value!r}")
    if parts.username or parts.password:
        raise ValueError("must not embed credentials; keep secrets out of project.yaml")
    return value


class Environment(BaseModel):
    """A named environment and the URL authorized for testing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: NonEmpty
    url: Annotated[NonEmpty, AfterValidator(_check_url)]


class Project(BaseModel):
    """Persistent description of a project under test.

    Unknown fields are rejected so credentials cannot be stored by accident.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: Annotated[NonEmpty, StringConstraints(max_length=100)]
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    repository: str = ""
    directory: str = ""
    environments: list[Environment] = Field(default_factory=list)
    frameworks: list[NonEmpty] = Field(default_factory=list)
    languages: list[NonEmpty] = Field(default_factory=list)
    commands: dict[NonEmpty, NonEmpty] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a timezone offset (ISO 8601)")
        return value

    @field_validator("environments")
    @classmethod
    def _unique_environments(cls, value: list[Environment]) -> list[Environment]:
        names = [environment.name.lower() for environment in value]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate environment names: {', '.join(duplicates)}")
        return value

    @property
    def archived(self) -> bool:
        return self.status is ProjectStatus.ARCHIVED
