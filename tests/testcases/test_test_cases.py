from pathlib import Path
from typing import Any

import pytest

from qa_workbench.requirements.coverage import coverage
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import (
    Step,
    TestCaseDraft,
    create_test_case,
    render_body,
    update_test_case,
)
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA

BOUNDARY = {"subject": "Age", "minimum": 18, "maximum": 65}


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(
        tmp_path / "project", [TEST_CASE_SCHEMA, REQUIREMENT_SCHEMA]
    )


def _draft(**overrides: Any) -> TestCaseDraft:
    values: dict[str, Any] = {
        "title": "Log in with valid credentials",
        "objective": "Validate access for a registered user.",
        "steps": [
            Step("Open the login page"),
            Step("Submit valid credentials", "The dashboard is shown"),
        ],
        "expected_result": "The user is authenticated.",
    }
    values.update(overrides)
    return TestCaseDraft(**values)


def _problems(repo: MarkdownRepository, **overrides: Any) -> str:
    with pytest.raises(RecordValidationError) as error:
        create_test_case(repo, _draft(**overrides))
    return "\n".join(error.value.problems)


def test_a_minimal_case_is_created_as_a_draft_with_defaults(
    repo: MarkdownRepository,
) -> None:
    record = create_test_case(repo, _draft())

    metadata = record.metadata
    assert record.id == "TC-001"
    assert metadata["status"] == "draft"
    assert metadata["priority"] == "medium"
    assert metadata["type"] == "functional"
    assert metadata["origin"] == "manual"
    assert metadata["steps"] == [
        {"action": "Open the login page"},
        {"action": "Submit valid credentials", "expected": "The dashboard is shown"},
    ]
    assert "criticality" not in metadata
    assert "tags" not in metadata


def test_every_field_of_the_specification_can_be_stored(
    repo: MarkdownRepository,
) -> None:
    draft = _draft(
        preconditions=["The application is available"],
        test_data=["User: $TEST_USER"],
        priority="high",
        criticality="critical",
        type="smoke",
        profile="Registered customer",
        environments=["staging", "qa"],
        requirements=["REQ-001"],
        issues=["ISSUE-007"],
        suites=["SUITE-001"],
        tags=["auth", "login"],
        origin="imported",
        author="Ana",
    )

    metadata = create_test_case(repo, draft).metadata

    assert metadata["criticality"] == "critical"
    assert metadata["profile"] == "Registered customer"
    assert metadata["environments"] == ["staging", "qa"]
    assert metadata["requirements"] == ["REQ-001"]
    assert metadata["issues"] == ["ISSUE-007"]
    assert metadata["suites"] == ["SUITE-001"]
    assert metadata["author"] == "Ana"
    assert metadata["created_at"].utcoffset() is not None
    assert metadata["updated_at"] == metadata["created_at"]


def test_the_body_is_readable_markdown_built_from_the_fields(
    repo: MarkdownRepository,
) -> None:
    record = create_test_case(
        repo,
        _draft(preconditions=["App is up"], test_data=["User: $TEST_USER"]),
    )

    assert record.body == (
        "# Log in with valid credentials\n\n"
        "## Objective\n\nValidate access for a registered user.\n\n"
        "## Preconditions\n\n- App is up\n\n"
        "## Test data\n\n- User: $TEST_USER\n\n"
        "## Steps\n\n"
        "1. Open the login page\n"
        "2. Submit valid credentials\n"
        "   - Expected: The dashboard is shown\n\n"
        "## Expected result\n\nThe user is authenticated.\n"
    )


def test_a_case_survives_a_roundtrip(repo: MarkdownRepository) -> None:
    created = create_test_case(repo, _draft(tags=["auth"]))

    assert repo.get(created.id).metadata == created.metadata
    assert repo.list_records("TC").errors == ()


def test_steps_and_an_expected_result_are_required(repo: MarkdownRepository) -> None:
    problems = _problems(repo, steps=[], expected_result="")

    assert "a test case needs at least one step (except exploratory)." in problems
    assert "expected_result is required (except exploratory)." in problems


def test_exploratory_cases_need_neither_steps_nor_an_expected_result(
    repo: MarkdownRepository,
) -> None:
    charter = {"mission": "Explore checkout", "timebox_minutes": 60, "areas": ["Cart"]}

    record = create_test_case(
        repo,
        _draft(
            steps=[],
            expected_result="",
            type="exploratory",
            techniques=["exploratory"],
            technique_data={"exploratory": charter},
        ),
    )

    assert "## Technique: exploratory\n\n- Cart: Explore checkout" in record.body


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("priority", "urgent", "priority 'urgent' is not allowed"),
        ("criticality", "huge", "criticality 'huge' is not allowed"),
        ("type", "magic", "type 'magic' is not allowed"),
        ("origin", "robot", "origin 'robot' is not allowed"),
    ],
)
def test_closed_choices_are_enforced(
    repo: MarkdownRepository, field: str, value: str, fragment: str
) -> None:
    assert fragment in _problems(repo, **{field: value})


def test_references_must_use_the_right_kind_of_id(repo: MarkdownRepository) -> None:
    problems = _problems(repo, requirements=["TC-001"], issues=["REQ-001"])

    assert "requirements must reference REQ ids, got TC-001." in problems
    assert "issues must reference ISSUE ids, got REQ-001." in problems


def test_title_and_objective_are_required(repo: MarkdownRepository) -> None:
    problems = _problems(repo, title="  ", objective="")

    assert "title is required." in problems
    assert "objective is required." in problems


def test_all_problems_are_reported_at_once(repo: MarkdownRepository) -> None:
    problems = _problems(repo, steps=[], priority="x", type="y")

    assert problems.count("\n") >= 2
    assert not (repo.root / "test-cases").exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"test_data": ["password=hunter2"]},
        {"steps": [Step("Type token=abc123 in the field")]},
        {"preconditions": ["api_key: AKIAABCDEFGHIJKLMNOP"]},
        {"objective": "Use ghp_" + "a" * 36},
    ],
)
def test_literal_secrets_are_refused(
    repo: MarkdownRepository, overrides: dict[str, Any]
) -> None:
    problems = _problems(repo, **overrides)

    assert "reference it by name instead" in problems


def test_placeholders_and_prose_about_passwords_are_fine(
    repo: MarkdownRepository,
) -> None:
    draft = _draft(
        steps=[Step("Enter the password and click Sign in")],
        test_data=["password=$TEST_PASSWORD", "token: <valid token>"],
    )

    assert create_test_case(repo, draft).id == "TC-001"


def test_unknown_techniques_are_refused(repo: MarkdownRepository) -> None:
    assert "technique 'guessing' is not supported" in _problems(
        repo, techniques=["guessing"]
    )


def test_technique_data_must_belong_to_a_declared_technique(
    repo: MarkdownRepository,
) -> None:
    problems = _problems(repo, technique_data={"decision_table": {}})

    assert (
        "technique_data has 'decision_table', which is not in techniques." in problems
    )


def test_invalid_technique_data_is_reported_with_the_reason(
    repo: MarkdownRepository,
) -> None:
    problems = _problems(
        repo,
        techniques=["boundary_value_analysis"],
        technique_data={
            "boundary_value_analysis": {"subject": "Age", "minimum": 9, "maximum": 1}
        },
    )

    assert "technique_data boundary_value_analysis:" in problems
    assert "minimum cannot be greater than maximum" in problems


def test_technique_data_is_rendered_as_derived_conditions(
    repo: MarkdownRepository,
) -> None:
    record = create_test_case(
        repo,
        _draft(
            techniques=["boundary_value_analysis"],
            technique_data={"boundary_value_analysis": BOUNDARY},
        ),
    )

    assert "## Technique: boundary value analysis" in record.body
    assert "- Age = 17: 17 (invalid)" in record.body
    assert "- Age = 18: 18\n" in record.body


def test_techniques_can_be_combined(repo: MarkdownRepository) -> None:
    record = create_test_case(
        repo,
        _draft(
            techniques=["boundary_value_analysis", "equivalence_partitioning"],
            technique_data={
                "boundary_value_analysis": BOUNDARY,
                "equivalence_partitioning": {
                    "subject": "Age",
                    "partitions": [
                        {"name": "adult", "valid": True, "examples": ["30"]},
                        {"name": "minor", "valid": False, "examples": ["10"]},
                    ],
                },
            },
        ),
    )

    assert "## Technique: boundary value analysis" in record.body
    assert "## Technique: equivalence partitioning" in record.body


def test_hand_edited_steps_are_validated_when_the_file_is_read(
    repo: MarkdownRepository,
) -> None:
    record = create_test_case(repo, _draft())
    record.path.write_text(
        record.path.read_text(encoding="utf-8").replace(
            "- action: Open the login page", "- surprise: 1"
        ),
        encoding="utf-8",
    )

    with pytest.raises(RecordValidationError, match="step 1 needs an action"):
        repo.get(record.id)


def test_update_changes_fields_and_rebuilds_the_body(
    repo: MarkdownRepository,
) -> None:
    created = create_test_case(repo, _draft())

    updated = update_test_case(
        repo,
        created.id,
        {"status": "in_review", "steps": [{"action": "Only step"}]},
    )

    assert updated.metadata["status"] == "in_review"
    assert "1. Only step" in updated.body
    assert "Submit valid credentials" not in updated.body
    assert repo.get(created.id).body == updated.body


def test_an_invalid_update_leaves_the_case_untouched(
    repo: MarkdownRepository,
) -> None:
    created = create_test_case(repo, _draft())
    before = created.path.read_text(encoding="utf-8")

    with pytest.raises(RecordValidationError, match="priority 'urgent'"):
        update_test_case(repo, created.id, {"priority": "urgent"})

    assert created.path.read_text(encoding="utf-8") == before


def test_render_body_tolerates_data_that_validation_will_reject() -> None:
    body = render_body(
        {
            "title": "T",
            "objective": "O",
            "steps": ["not a mapping", {"action": "ok"}],
            "technique_data": {"decision_table": {"bad": True}},
            "preconditions": "not a list",
        }
    )

    assert "2. ok" in body
    assert "Technique" not in body


def test_a_case_covers_the_requirement_it_names(repo: MarkdownRepository) -> None:
    repo.create(
        "REQ",
        {"title": "Login", "status": "draft", "source": "x.md", "origin": "manual"},
        "# Login\n",
    )
    case = create_test_case(repo, _draft(requirements=["REQ-001"]))

    (item,) = coverage(repo)

    assert item.covered
    assert item.cases == (case.id,)


def test_an_estimate_in_minutes_can_be_stored(repo: MarkdownRepository) -> None:
    record = create_test_case(repo, _draft(estimated_minutes=15))

    assert record.metadata["estimated_minutes"] == 15


@pytest.mark.parametrize("value", [0, -5])
def test_an_estimate_must_be_a_positive_whole_number(
    repo: MarkdownRepository, value: int
) -> None:
    assert "estimated_minutes must be a whole number of minutes" in _problems(
        repo, estimated_minutes=value
    )
