from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from qa_workbench.projects.models import Environment, Project, ProjectStatus

NOW = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def _project(**overrides: Any) -> Project:
    values: dict[str, Any] = {
        "id": "PROJ-001",
        "name": "Shop",
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return Project(**values)


def test_minimal_project_is_active_with_empty_collections() -> None:
    project = _project()

    assert project.status is ProjectStatus.ACTIVE
    assert not project.archived
    assert project.environments == []
    assert project.commands == {}


def test_all_project_details_are_stored() -> None:
    project = _project(
        description="Storefront",
        repository="acme/shop",
        directory="C:/work/shop",
        environments=[Environment(name="staging", url="https://staging.example.com")],
        frameworks=["django"],
        languages=["python"],
        commands={"test": "pytest"},
    )

    assert project.environments[0].url == "https://staging.example.com"
    assert project.commands["test"] == "pytest"


@pytest.mark.parametrize("project_id", ["", "PROJ-1", "proj-001", "TC-001", "PROJ-abc"])
def test_malformed_ids_are_rejected(project_id: str) -> None:
    with pytest.raises(ValidationError, match="id"):
        _project(id=project_id)


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        _project(name=name)


def test_name_is_trimmed() -> None:
    assert _project(name="  Shop  ").name == "Shop"


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _project(created_at=datetime(2026, 1, 1, 10, 0))


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "example.com", "http://", "https://user:secret@example.com"],
)
def test_unsafe_or_malformed_environment_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Environment(name="staging", url=url)


def test_credentials_in_urls_are_explained() -> None:
    with pytest.raises(ValidationError, match="must not embed credentials"):
        Environment(name="staging", url="https://user:secret@example.com")


def test_duplicate_environment_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate environment names: staging"):
        _project(
            environments=[
                Environment(name="staging", url="https://a.example.com"),
                Environment(name="Staging", url="https://b.example.com"),
            ]
        )


def test_unknown_fields_cannot_smuggle_secrets() -> None:
    with pytest.raises(ValidationError, match="token"):
        _project(token="ghp_secret")
