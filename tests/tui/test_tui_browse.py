from pathlib import Path

import pytest
from test_tui_data import _case

from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui.browse import (
    ALL,
    BrowseRow,
    case_detail,
    case_rows,
    filter_rows,
    requirement_detail,
    requirement_rows,
)
from qa_workbench.workspace import repository_for


@pytest.fixture
def repo(tmp_path: Path):
    project = ProjectRepository(tmp_path).create("Demo")
    return repository_for(tmp_path, project)


def _requirement(repo, title="Users can log in", **extra):
    fields = {
        "title": title,
        "status": "approved",
        "source": "spec.md",
        "origin": "manual",
        "priority": "high",
        **extra,
    }
    return repo.create("REQ", fields, f"# {title}\n\nThe system must allow it.\n")


def test_filter_matches_every_word_status_and_ignores_case() -> None:
    rows = [
        BrowseRow("TC-001", ("TC-001",), "active", "tc-001 login with card active"),
        BrowseRow("TC-002", ("TC-002",), "draft", "tc-002 login with cash draft"),
        BrowseRow("TC-003", ("TC-003",), "active", "tc-003 logout"),
    ]

    assert [r.key for r in filter_rows(rows, "", ALL)] == ["TC-001", "TC-002", "TC-003"]
    assert [r.key for r in filter_rows(rows, "LOGIN card", ALL)] == ["TC-001"]
    assert [r.key for r in filter_rows(rows, "login", "draft")] == ["TC-002"]
    assert filter_rows(rows, "nothing", ALL) == []
    assert [r.key for r in filter_rows(rows, "   ", "active")] == ["TC-001", "TC-003"]


def test_requirement_rows_say_whether_a_case_covers_each(repo) -> None:
    covered = _requirement(repo, "Users can log in", tags=["auth"])
    _requirement(repo, "Users can log out")
    case = _case(repo)
    repo.update(case.id, {"requirements": [covered.id]})

    data = requirement_rows(repo)

    cells = {row.key: row.cells for row in data.rows}
    assert cells["REQ-001"][3] == "1 case(s)" and cells["REQ-002"][3] == "NOT COVERED"
    assert cells["REQ-001"][1] == "high" and cells["REQ-001"][2] == "approved"
    assert "auth" in data.rows[0].search and data.problems == ()


def test_requirement_detail_lists_criteria_cases_and_missing_ones(repo) -> None:
    requirement = _requirement(
        repo,
        acceptance_criteria=["Name is required", "Date is valid"],
        cases=["TC-099"],
    )
    case = _case(repo, "Valid registration")
    repo.update(case.id, {"requirements": [requirement.id]})

    text = requirement_detail(repo, requirement.id)

    assert "ACCEPTANCE CRITERIA" in text and "  - Name is required" in text
    assert f"{case.id}  Valid registration" in text
    assert "NAMED BUT MISSING" in text and "TC-099" in text
    assert "The system must allow it." in text


def test_the_description_does_not_repeat_the_criteria(repo) -> None:
    requirement = repo.create(
        "REQ",
        {
            "title": "Pay",
            "status": "draft",
            "source": "s.md",
            "origin": "manual",
            "acceptance_criteria": ["Receipt is emailed"],
        },
        "# Pay\n\nA description.\n\n## Acceptance criteria\n\n- Receipt is emailed\n",
    )

    text = requirement_detail(repo, requirement.id)

    assert text.count("Receipt is emailed") == 1 and "A description." in text


def test_a_requirement_without_cases_or_criteria_says_so(repo) -> None:
    requirement = _requirement(repo)

    text = requirement_detail(repo, requirement.id)

    assert "(no test case covers this)" in text and "(none)" in text


def test_case_rows_and_detail(repo) -> None:
    case = _case(repo, "Customer can log in")
    repo.update(case.id, {"requirements": ["REQ-001"], "tags": ["smoke"]})

    row = case_rows(repo).rows[0]
    text = case_detail(repo, case.id)

    assert row.cells == (
        case.id,
        "medium",
        "active",
        "functional",
        "Customer can log in",
    )
    assert "smoke" in row.search and "req-001" in row.search
    assert "1. Open the page" in text and "Requirements: REQ-001" in text
    assert "EXPECTED RESULT\n  The dashboard is shown." in text


def test_damaged_requirements_and_cases_are_reported_not_listed(repo) -> None:
    _requirement(repo)
    _requirement(repo, "Other")
    repo.path_of("REQ-002").write_text("garbage", encoding="utf-8")
    _case(repo)
    _case(repo, "Other case")
    repo.path_of("TC-002").write_text("garbage", encoding="utf-8")

    requirements, cases = requirement_rows(repo), case_rows(repo)

    assert [r.key for r in requirements.rows] == ["REQ-001"]
    assert len(requirements.problems) == 1 and requirements.problems[0].startswith(
        "REQ:"
    )
    assert [r.key for r in cases.rows] == ["TC-001"]
    assert len(cases.problems) == 1 and cases.problems[0].startswith("TC:")
