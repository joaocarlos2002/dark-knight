from pathlib import Path
from typing import Any

import pytest

from qa_workbench.plans.builder import PlanDraft, create_plan, set_selection
from qa_workbench.plans.schema import TEST_PLAN_SCHEMA
from qa_workbench.plans.selection import NOT_CONSIDERED, recommend
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    repository = MarkdownRepository(
        tmp_path / "project", [REQUIREMENT_SCHEMA, TEST_CASE_SCHEMA, TEST_PLAN_SCHEMA]
    )
    for title in ("Login", "Checkout", "Reports"):
        repository.create(
            "REQ",
            {"title": title, "status": "draft", "source": "x.md", "origin": "manual"},
        )
    return repository


def _case(repo: MarkdownRepository, **overrides: Any):
    values: dict[str, Any] = {
        "title": "Case",
        "objective": "Validate",
        "steps": [Step("Do it")],
        "expected_result": "Done",
    }
    status = overrides.pop("status", "active")
    values.update(overrides)
    return create_test_case(repo, TestCaseDraft(**values), status=status)


def _by_id(recommendation):
    return {item.id: item for item in recommendation.items}


def _factors(item) -> list[str]:
    return [reason.factor for reason in item.reasons]


def test_a_case_covering_a_changed_requirement_is_included_with_the_reason(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-001"])

    item = _by_id(recommend(repo, changed_requirements=["REQ-001"]))["TC-001"]

    assert item.decision == "include"
    assert item.source == "rules"
    assert ("changed_requirements", "covers changed REQ-001") in [
        (r.factor, r.detail) for r in item.reasons
    ]


def test_the_only_case_covering_a_changed_requirement_gets_a_coverage_reason(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-001"])
    _case(repo, requirements=["REQ-002"])
    _case(repo, requirements=["REQ-002"])

    result = _by_id(recommend(repo, changed_requirements=["REQ-001", "REQ-002"]))

    assert "coverage" in _factors(result["TC-001"])
    assert "coverage" not in _factors(result["TC-002"])
    assert "coverage" not in _factors(result["TC-003"])


def test_unrelated_cases_are_excluded_and_say_why(repo: MarkdownRepository) -> None:
    _case(repo, requirements=["REQ-001"])
    _case(repo, requirements=["REQ-002"])

    item = _by_id(recommend(repo, changed_requirements=["REQ-001"]))["TC-002"]

    assert item.decision == "exclude"
    assert _factors(item) == ["changed_requirements"]
    assert "not related to the changed requirements" in item.reasons[0].detail


def test_critical_and_high_priority_cases_are_included_even_if_unrelated(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-002"], priority="high")
    _case(repo, requirements=["REQ-002"], criticality="critical")
    _case(repo, requirements=["REQ-002"], priority="low")

    result = _by_id(recommend(repo, changed_requirements=["REQ-001"]))

    assert result["TC-001"].decision == "include"
    assert result["TC-001"].reasons[0].detail == "marked high priority"
    assert result["TC-002"].decision == "include"
    assert result["TC-002"].reasons[0].detail == "marked critical"
    assert result["TC-003"].decision == "exclude"


@pytest.mark.parametrize("kind", ["smoke", "sanity"])
def test_baseline_cases_guard_the_build(repo: MarkdownRepository, kind: str) -> None:
    _case(repo, type=kind)

    item = _by_id(recommend(repo))["TC-001"]

    assert item.decision == "include"
    assert _factors(item) == ["regression_risk"]


def test_cases_that_are_not_active_are_excluded_as_not_ready(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-001"], status="draft")

    item = _by_id(recommend(repo, changed_requirements=["REQ-001"]))["TC-001"]

    assert item.decision == "exclude"
    assert (item.reasons[0].factor, item.reasons[0].detail) == (
        "readiness",
        "the case is draft, not active",
    )


def test_every_case_gets_a_decision_and_every_decision_has_reasons(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-001"])
    _case(repo, requirements=["REQ-002"], status="draft")
    _case(repo, type="smoke")
    _case(repo, requirements=["REQ-003"])

    recommendation = recommend(repo, changed_requirements=["REQ-001"])

    assert [item.id for item in recommendation.items] == [
        "TC-001",
        "TC-002",
        "TC-003",
        "TC-004",
    ]
    assert all(item.reasons for item in recommendation.items)


def test_the_recommendation_says_what_it_could_not_consider(
    repo: MarkdownRepository,
) -> None:
    recommendation = recommend(repo)

    assert recommendation.notes == NOT_CONSIDERED
    assert any(note.startswith("defect_history") for note in recommendation.notes)
    assert any(note.startswith("previous_results") for note in recommendation.notes)


def test_a_time_budget_keeps_the_most_relevant_cases_first(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-002"], priority="high", estimated_minutes=30)
    _case(repo, requirements=["REQ-001"], estimated_minutes=30)
    _case(repo, requirements=["REQ-001"], estimated_minutes=30)

    recommendation = recommend(
        repo, changed_requirements=["REQ-001"], time_budget_minutes=60
    )
    result = _by_id(recommendation)

    assert result["TC-002"].decision == "include"
    assert result["TC-003"].decision == "include"
    assert result["TC-001"].decision == "exclude"
    assert result["TC-001"].reasons[0].factor == "time"
    assert "would exceed the 60 min budget (60 min already used)" in (
        result["TC-001"].reasons[0].detail
    )
    assert recommendation.minutes_used == 60


def test_included_cases_within_the_budget_say_so(repo: MarkdownRepository) -> None:
    _case(repo, requirements=["REQ-001"], estimated_minutes=10)

    item = _by_id(
        recommend(repo, changed_requirements=["REQ-001"], time_budget_minutes=60)
    )["TC-001"]

    assert ("time", "10 min, within the budget") in [
        (r.factor, r.detail) for r in item.reasons
    ]


def test_cases_without_an_estimate_are_not_counted_against_the_budget(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-001"])

    recommendation = recommend(
        repo, changed_requirements=["REQ-001"], time_budget_minutes=5
    )

    item = _by_id(recommendation)["TC-001"]
    assert item.decision == "include"
    assert "no estimate, so it is not counted against the budget" in (
        item.reasons[-1].detail
    )
    assert recommendation.minutes_used == 0


def test_no_budget_means_no_time_reasons(repo: MarkdownRepository) -> None:
    _case(repo, requirements=["REQ-001"], estimated_minutes=10)

    item = _by_id(recommend(repo, changed_requirements=["REQ-001"]))["TC-001"]

    assert "time" not in _factors(item)


def test_invalid_input_is_refused(repo: MarkdownRepository) -> None:
    with pytest.raises(ValueError, match="at least 1 minute"):
        recommend(repo, time_budget_minutes=0)
    with pytest.raises(ValueError, match="Unknown changed requirement"):
        recommend(repo, changed_requirements=["REQ-099"])


def test_a_project_without_cases_gives_an_empty_recommendation(
    repo: MarkdownRepository,
) -> None:
    assert recommend(repo, changed_requirements=["REQ-001"]).items == ()


def test_a_recommendation_can_be_stored_on_a_plan_and_read_back(
    repo: MarkdownRepository,
) -> None:
    _case(repo, requirements=["REQ-001"], estimated_minutes=10)
    _case(repo, requirements=["REQ-002"])
    plan = create_plan(
        repo,
        PlanDraft(
            title="Plan",
            scope="s",
            strategy="s",
            objectives=["o"],
            entry_criteria=["e"],
            exit_criteria=["x"],
        ),
    )
    recommendation = recommend(repo, changed_requirements=["REQ-001"])

    stored = set_selection(repo, plan.id, recommendation.to_fields())

    selection = repo.get(plan.id).metadata["selection"]
    assert [(i["id"], i["decision"], i["source"]) for i in selection] == [
        ("TC-001", "include", "rules"),
        ("TC-002", "exclude", "rules"),
    ]
    assert "### Include TC-001" in stored.body
    assert "### Exclude TC-002" in stored.body
