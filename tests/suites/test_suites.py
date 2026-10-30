from pathlib import Path

import pytest

from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.suites.schema import SUITE_SCHEMA
from qa_workbench.suites.service import (
    SuiteError,
    add_cases,
    create_suite,
    membership,
    remove_cases,
    summarize,
    verify_suite,
)
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [TEST_CASE_SCHEMA, SUITE_SCHEMA])


def _case(repo: MarkdownRepository, title: str = "Case", **overrides: object):
    status = overrides.pop("status", "active")
    values = {
        "title": title,
        "objective": "Validate",
        "steps": [Step("Do it")],
        "expected_result": "Done",
        **overrides,
    }
    return create_test_case(repo, TestCaseDraft(**values), status=str(status))


def test_a_suite_is_created_as_a_draft_with_its_type(repo: MarkdownRepository) -> None:
    suite = create_suite(repo, "Smoke", "smoke", description="Fast checks", tags=["ci"])

    assert suite.id == "SUITE-001"
    assert suite.metadata["status"] == "draft"
    assert suite.metadata["type"] == "smoke"
    assert suite.metadata["description"] == "Fast checks"
    assert suite.metadata["tags"] == ["ci"]
    assert "cases" not in suite.metadata
    assert suite.path == repo.root / "test-suites" / "SUITE-001.md"


@pytest.mark.parametrize(
    "suite_type",
    [
        "smoke",
        "sanity",
        "regression",
        "end_to_end",
        "integration",
        "api",
        "functional",
        "security",
        "compatibility",
        "acceptance",
        "custom",
    ],
)
def test_every_suite_type_of_the_specification_is_accepted(
    repo: MarkdownRepository, suite_type: str
) -> None:
    assert create_suite(repo, "S", suite_type).metadata["type"] == suite_type


def test_invalid_suites_are_refused(repo: MarkdownRepository) -> None:
    with pytest.raises(RecordValidationError, match="type 'magic' is not allowed"):
        create_suite(repo, "S", "magic")
    with pytest.raises(RecordValidationError, match="title is required"):
        create_suite(repo, " ", "smoke")


def test_the_body_links_the_cases_for_obsidian(repo: MarkdownRepository) -> None:
    case = _case(repo, "Log in")

    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])

    assert suite.body == "# Smoke\n\n## Cases\n\n- [[TC-001]] Log in\n"


def test_a_case_can_belong_to_several_suites(repo: MarkdownRepository) -> None:
    case = _case(repo, "Log in")
    smoke = create_suite(repo, "Smoke", "smoke", cases=[case.id])
    regression = create_suite(repo, "Regression", "regression", cases=[case.id])

    members = membership(repo)

    assert members.suite_cases == {smoke.id: (case.id,), regression.id: (case.id,)}
    assert members.case_suites == {case.id: (smoke.id, regression.id)}


def test_a_suite_holds_many_cases(repo: MarkdownRepository) -> None:
    first, second = _case(repo, "A"), _case(repo, "B")
    suite = create_suite(repo, "Smoke", "smoke", cases=[first.id, second.id])

    assert membership(repo).suite_cases[suite.id] == (first.id, second.id)


def test_cases_must_exist(repo: MarkdownRepository) -> None:
    with pytest.raises(SuiteError, match="do not exist: TC-099"):
        create_suite(repo, "Smoke", "smoke", cases=["TC-099"])

    assert repo.record_ids("SUITE") == []


def test_only_test_cases_can_be_members(repo: MarkdownRepository) -> None:
    _case(repo)

    with pytest.raises(SuiteError, match="do not exist: REQ-001"):
        create_suite(repo, "Smoke", "smoke", cases=["REQ-001"])


def test_cases_are_added_to_an_existing_suite(repo: MarkdownRepository) -> None:
    first, second = _case(repo, "A"), _case(repo, "B")
    suite = create_suite(repo, "Smoke", "smoke", cases=[first.id])

    updated = add_cases(repo, suite.id, [second.id])

    assert updated.metadata["cases"] == [first.id, second.id]
    assert "- [[TC-002]] B" in updated.body
    assert repo.get(suite.id).metadata["cases"] == [first.id, second.id]


def test_adding_a_case_that_is_already_there_is_refused(
    repo: MarkdownRepository,
) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])

    with pytest.raises(SuiteError, match="already contains: TC-001"):
        add_cases(repo, suite.id, [case.id])


def test_adding_the_same_case_twice_in_one_call_is_refused(
    repo: MarkdownRepository,
) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke")

    with pytest.raises(SuiteError, match="more than once"):
        add_cases(repo, suite.id, [case.id, case.id])

    assert repo.get(suite.id).metadata.get("cases") is None


def test_adding_a_missing_case_is_refused_and_changes_nothing(
    repo: MarkdownRepository,
) -> None:
    suite = create_suite(repo, "Smoke", "smoke")
    before = suite.path.read_text(encoding="utf-8")

    with pytest.raises(SuiteError, match="do not exist: TC-042"):
        add_cases(repo, suite.id, ["TC-042"])

    assert suite.path.read_text(encoding="utf-8") == before


def test_cases_are_removed_without_touching_them(repo: MarkdownRepository) -> None:
    first, second = _case(repo, "A"), _case(repo, "B")
    suite = create_suite(repo, "Smoke", "smoke", cases=[first.id, second.id])
    before = first.path.read_text(encoding="utf-8")

    updated = remove_cases(repo, suite.id, [first.id])

    assert updated.metadata["cases"] == [second.id]
    assert "TC-001" not in updated.body
    assert first.path.read_text(encoding="utf-8") == before


def test_removing_the_last_case_leaves_an_empty_suite(
    repo: MarkdownRepository,
) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])

    updated = remove_cases(repo, suite.id, [case.id])

    assert updated.metadata["cases"] == []
    assert "## Cases" not in updated.body
    assert membership(repo).suite_cases == {suite.id: ()}


def test_removing_a_case_that_is_not_a_member_is_refused(
    repo: MarkdownRepository,
) -> None:
    suite = create_suite(repo, "Smoke", "smoke")

    with pytest.raises(SuiteError, match="does not contain: TC-001"):
        remove_cases(repo, suite.id, ["TC-001"])


def test_a_case_may_name_its_suites_and_membership_is_the_union(
    repo: MarkdownRepository,
) -> None:
    suite = create_suite(repo, "Smoke", "smoke")
    declared_by_case = _case(repo, "A", suites=[suite.id])
    declared_by_suite = _case(repo, "B")
    add_cases(repo, suite.id, [declared_by_suite.id])
    both = _case(repo, "C", suites=[suite.id])
    add_cases(repo, suite.id, [both.id])

    members = membership(repo)

    assert members.suite_cases[suite.id] == (
        declared_by_case.id,
        declared_by_suite.id,
        both.id,
    )
    assert members.case_suites[both.id] == (suite.id,)


def test_membership_ignores_records_that_do_not_exist(
    repo: MarkdownRepository,
) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])
    case.path.unlink()

    assert membership(repo).suite_cases == {suite.id: ()}
    assert membership(repo).case_suites == {}


def test_membership_of_a_project_without_suites_is_empty(
    repo: MarkdownRepository,
) -> None:
    _case(repo)

    members = membership(repo)

    assert members.suite_cases == {}
    assert members.case_suites == {}


def test_summaries_list_every_suite_with_its_cases(repo: MarkdownRepository) -> None:
    case = _case(repo)
    create_suite(repo, "Smoke", "smoke", cases=[case.id])
    create_suite(repo, "Regression", "regression")

    summaries = summarize(repo)

    assert [(s.id, s.type, s.cases) for s in summaries] == [
        ("SUITE-001", "smoke", ("TC-001",)),
        ("SUITE-002", "regression", ()),
    ]


def test_verify_reports_missing_and_not_yet_active_cases(
    repo: MarkdownRepository,
) -> None:
    ready = _case(repo, "Ready")
    draft = _case(repo, "Draft", status="draft")
    gone = _case(repo, "Gone")
    suite = create_suite(repo, "Smoke", "smoke", cases=[ready.id, draft.id, gone.id])
    gone.path.unlink()

    result = verify_suite(repo, suite.id)

    assert result.missing == (gone.id,)
    assert result.not_active == (draft.id,)
    assert not result.ok


def test_a_sound_suite_verifies(repo: MarkdownRepository) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])

    assert verify_suite(repo, suite.id).ok


def test_a_suite_with_duplicate_cases_written_by_hand_is_rejected(
    repo: MarkdownRepository,
) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])
    suite.path.write_text(
        suite.path.read_text(encoding="utf-8").replace(
            "cases: [TC-001]", "cases: [TC-001, TC-001]"
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecordValidationError, match="same case more than once"):
        repo.get(suite.id)


def test_without_test_case_records_nothing_is_claimed_about_cases(
    tmp_path: Path,
) -> None:
    repo = MarkdownRepository(tmp_path, [SUITE_SCHEMA])

    suite = create_suite(repo, "Smoke", "smoke", cases=["TC-001"])

    assert verify_suite(repo, suite.id).ok
    assert membership(repo).suite_cases == {suite.id: ()}
