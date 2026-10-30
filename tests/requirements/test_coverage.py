from pathlib import Path

import pytest

from qa_workbench.requirements.coverage import coverage
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.storage.validation import RecordSchema

CASES = RecordSchema(
    prefix="TC",
    directory="test-cases",
    statuses=frozenset({"draft", "active"}),
    required=("title",),
    references={"requirements": ("REQ",)},
)


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [REQUIREMENT_SCHEMA, CASES])


def _requirement(repo: MarkdownRepository, title: str, **extra: object):
    return repo.create(
        "REQ", {"title": title, "status": "draft", "source": "x.md", **extra}
    )


def _case(repo: MarkdownRepository, **extra: object):
    return repo.create("TC", {"title": "Case", "status": "draft", **extra})


def test_a_requirement_with_no_cases_is_not_covered(repo: MarkdownRepository) -> None:
    _requirement(repo, "Login")

    (item,) = coverage(repo)

    assert (item.id, item.covered, item.cases) == ("REQ-001", False, ())


def test_a_case_that_names_the_requirement_covers_it(
    repo: MarkdownRepository,
) -> None:
    _requirement(repo, "Login")
    case = _case(repo, requirements=["REQ-001"])

    (item,) = coverage(repo)

    assert item.covered
    assert item.cases == (case.id,)


def test_a_requirement_that_names_the_case_is_covered_too(
    repo: MarkdownRepository,
) -> None:
    case = _case(repo)
    _requirement(repo, "Login", cases=[case.id])

    (item,) = coverage(repo)

    assert item.cases == (case.id,)


def test_both_directions_are_merged_without_duplicates(
    repo: MarkdownRepository,
) -> None:
    first = _case(repo, requirements=["REQ-001"])
    second = _case(repo)
    _requirement(repo, "Login", cases=[first.id, second.id])

    (item,) = coverage(repo)

    assert item.cases == (first.id, second.id)


def test_cases_that_do_not_exist_are_reported_not_counted(
    repo: MarkdownRepository,
) -> None:
    _requirement(repo, "Login", cases=["TC-099"])

    (item,) = coverage(repo)

    assert not item.covered
    assert item.missing_cases == ("TC-099",)


def test_coverage_is_per_requirement_and_ordered(repo: MarkdownRepository) -> None:
    _requirement(repo, "A")
    _requirement(repo, "B")
    _case(repo, requirements=["REQ-002"])

    report = coverage(repo)

    assert [(r.id, r.covered) for r in report] == [
        ("REQ-001", False),
        ("REQ-002", True),
    ]
    assert [r.title for r in report] == ["A", "B"]


def test_without_a_case_schema_nothing_is_claimed_about_cases(
    tmp_path: Path,
) -> None:
    repo = MarkdownRepository(tmp_path, [REQUIREMENT_SCHEMA])
    repo.create(
        "REQ", {"title": "Login", "status": "draft", "source": "x", "cases": ["TC-001"]}
    )

    (item,) = coverage(repo)

    assert item.missing_cases == ()
    assert item.cases == ("TC-001",)


def test_no_requirements_means_an_empty_report(repo: MarkdownRepository) -> None:
    assert coverage(repo) == []
