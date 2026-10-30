from pathlib import Path

import pytest
import yaml

from qa_workbench.projects.errors import (
    InvalidProjectError,
    ProjectNotFoundError,
    ProjectStateError,
)
from qa_workbench.projects.models import Environment, ProjectStatus
from qa_workbench.projects.repository import ProjectRepository


@pytest.fixture
def repository(tmp_path: Path) -> ProjectRepository:
    return ProjectRepository(tmp_path / "data")


def test_create_writes_project_yaml_and_readme(repository: ProjectRepository) -> None:
    project = repository.create(
        "Shop",
        description="Storefront",
        repository="acme/shop",
        directory="C:/work/shop",
        environments=[Environment(name="staging", url="https://staging.example.com")],
        frameworks=["django"],
        languages=["python"],
        commands={"test": "pytest"},
    )

    folder = repository.root / "PROJ-001"
    document = yaml.safe_load((folder / "project.yaml").read_text(encoding="utf-8"))
    assert project.id == "PROJ-001"
    assert document["name"] == "Shop"
    assert document["status"] == "active"
    assert document["environments"] == [
        {"name": "staging", "url": "https://staging.example.com"}
    ]
    assert document["commands"] == {"test": "pytest"}
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert "PROJ-001" in readme
    assert "Storefront" in readme


def test_ids_increase_and_are_never_reused(repository: ProjectRepository) -> None:
    first = repository.create("One")
    second = repository.create("Two")
    repository.archive(first.id)
    third = repository.create("Three")

    assert [first.id, second.id, third.id] == ["PROJ-001", "PROJ-002", "PROJ-003"]


def test_timestamps_carry_a_timezone(repository: ProjectRepository) -> None:
    project = repository.create("Shop")

    assert project.created_at.utcoffset() is not None
    assert project.created_at == project.updated_at


def test_open_returns_what_was_created(repository: ProjectRepository) -> None:
    created = repository.create("Shop", frameworks=["django"])

    assert repository.open(created.id) == created


def test_list_hides_archived_projects_unless_requested(
    repository: ProjectRepository,
) -> None:
    keep = repository.create("Keep")
    gone = repository.create("Gone")
    repository.archive(gone.id)

    assert [p.id for p in repository.list_projects().projects] == [keep.id]
    everything = repository.list_projects(include_archived=True).projects
    assert [p.id for p in everything] == [keep.id, gone.id]


def test_list_on_a_fresh_data_dir_is_empty(repository: ProjectRepository) -> None:
    listing = repository.list_projects()

    assert listing.projects == ()
    assert listing.errors == ()


def test_archive_keeps_files_and_updates_the_record(
    repository: ProjectRepository,
) -> None:
    created = repository.create("Shop")

    archived = repository.archive(created.id)

    assert archived.status is ProjectStatus.ARCHIVED
    assert archived.updated_at >= created.updated_at
    assert (repository.root / created.id / "README.md").is_file()
    assert repository.open(created.id).archived


def test_archiving_twice_is_an_error(repository: ProjectRepository) -> None:
    project = repository.create("Shop")
    repository.archive(project.id)

    with pytest.raises(ProjectStateError, match="already archived"):
        repository.archive(project.id)


@pytest.mark.parametrize("project_id", ["PROJ-999", "nope", "../escape", ""])
def test_unknown_or_malformed_ids_are_not_found(
    repository: ProjectRepository, project_id: str
) -> None:
    with pytest.raises(ProjectNotFoundError):
        repository.open(project_id)


def test_invalid_input_is_rejected_and_nothing_is_written(
    repository: ProjectRepository,
) -> None:
    with pytest.raises(InvalidProjectError, match="name"):
        repository.create("   ")

    assert repository.list_projects().projects == ()
    assert not any(repository.root.iterdir())


def test_invalid_command_is_rejected_and_nothing_is_written(
    repository: ProjectRepository,
) -> None:
    with pytest.raises(InvalidProjectError, match="commands"):
        repository.create("Shop", commands={"test": "  "})

    assert not any(repository.root.iterdir())


def _corrupt(repository: ProjectRepository, project_id: str, text: str) -> Path:
    path = repository.root / project_id / "project.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_malformed_yaml_reports_the_file(repository: ProjectRepository) -> None:
    project = repository.create("Shop")
    path = _corrupt(repository, project.id, "name: [unclosed\n")

    with pytest.raises(InvalidProjectError) as error:
        repository.open(project.id)

    assert str(path) in str(error.value)
    assert isinstance(error.value.__cause__, yaml.YAMLError)


def test_non_mapping_yaml_is_rejected(repository: ProjectRepository) -> None:
    project = repository.create("Shop")
    _corrupt(repository, project.id, "- just\n- a list\n")

    with pytest.raises(InvalidProjectError, match="mapping of fields"):
        repository.open(project.id)


def test_hand_edited_secret_field_is_rejected(repository: ProjectRepository) -> None:
    project = repository.create("Shop")
    path = repository.root / project.id / "project.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "token: ghp_x\n", "utf-8")

    with pytest.raises(InvalidProjectError, match="token"):
        repository.open(project.id)


def test_id_must_match_its_folder(repository: ProjectRepository) -> None:
    first = repository.create("One")
    second = repository.create("Two")
    path = repository.root / second.id / "project.yaml"
    path.write_text(
        (repository.root / first.id / "project.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(InvalidProjectError, match="does not match its folder"):
        repository.open(second.id)


def test_list_reports_corrupt_projects_instead_of_hiding_them(
    repository: ProjectRepository,
) -> None:
    good = repository.create("Good")
    bad = repository.create("Bad")
    _corrupt(repository, bad.id, "name: [unclosed\n")

    listing = repository.list_projects()

    assert [p.id for p in listing.projects] == [good.id]
    assert len(listing.errors) == 1
    assert bad.id in str(listing.errors[0])


def test_unrelated_folders_are_ignored(repository: ProjectRepository) -> None:
    repository.create("Shop")
    (repository.root / "notes").mkdir()
    (repository.root / "stray.txt").write_text("x", encoding="utf-8")

    listing = repository.list_projects()

    assert len(listing.projects) == 1
    assert listing.errors == ()
