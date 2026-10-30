from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from qa_workbench.plans.builder import (
    PlanDraft,
    Risk,
    create_plan,
    set_selection,
    update_plan,
)
from qa_workbench.plans.schema import TEST_PLAN_SCHEMA
from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.repository import MarkdownRepository

START = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [TEST_PLAN_SCHEMA])


def _draft(**overrides: Any) -> PlanDraft:
    values: dict[str, Any] = {
        "title": "Release 1.4 regression",
        "scope": "Checkout and account flows of release 1.4.",
        "strategy": "Risk-based regression with smoke first.",
        "objectives": ["Confirm no regression in checkout"],
        "entry_criteria": ["Build deployed to staging"],
        "exit_criteria": ["No open critical defects"],
    }
    values.update(overrides)
    return PlanDraft(**values)


def _problems(repo: MarkdownRepository, **overrides: Any) -> str:
    with pytest.raises(RecordValidationError) as error:
        create_plan(repo, _draft(**overrides))
    return "\n".join(error.value.problems)


def test_a_minimal_plan_is_created_as_a_draft(repo: MarkdownRepository) -> None:
    record = create_plan(repo, _draft())

    metadata = record.metadata
    assert record.id == "TP-001"
    assert metadata["status"] == "draft"
    assert metadata["origin"] == "manual"
    assert metadata["objectives"] == ["Confirm no regression in checkout"]
    assert "risks" not in metadata
    assert "schedule" not in metadata


def test_every_field_of_the_specification_can_be_stored(
    repo: MarkdownRepository,
) -> None:
    draft = _draft(
        in_scope=["Checkout"],
        out_of_scope=["Admin area"],
        levels=["system", "acceptance"],
        test_types=["functional", "regression"],
        environments=["staging"],
        profiles=["Registered customer"],
        data=["User: $TEST_USER"],
        dependencies=["Payment sandbox available"],
        risks=[
            Risk("Sandbox instability", "medium", "Retry once"),
            Risk("Late build", "high"),
        ],
        suites=["SUITE-001"],
        owners=["Ana", "Bruno"],
        schedule_start=START,
        schedule_end=START + timedelta(days=5),
    )

    metadata = create_plan(repo, draft).metadata

    assert metadata["risks"] == [
        {
            "description": "Sandbox instability",
            "level": "medium",
            "mitigation": "Retry once",
        },
        {"description": "Late build", "level": "high"},
    ]
    assert metadata["schedule"]["end"] == START + timedelta(days=5)
    assert metadata["owners"] == ["Ana", "Bruno"]
    assert metadata["suites"] == ["SUITE-001"]


def test_the_body_is_readable_markdown(repo: MarkdownRepository) -> None:
    record = create_plan(
        repo,
        _draft(
            in_scope=["Checkout"],
            risks=[Risk("Late build", "high", "Freeze early")],
            schedule_start=START,
            schedule_end=START + timedelta(days=1),
        ),
    )

    assert record.body.startswith("# Release 1.4 regression\n\n## Scope\n\n")
    assert "## In scope\n\n- Checkout" in record.body
    assert "## Risks\n\n- [high] Late build Mitigation: Freeze early" in record.body
    assert "- Start: 2026-03-01T09:00:00+00:00" in record.body
    assert "## Exit criteria\n\n- No open critical defects" in record.body


def test_a_plan_survives_a_roundtrip(repo: MarkdownRepository) -> None:
    created = create_plan(
        repo, _draft(owners=["Ana"], schedule_start=START, schedule_end=START)
    )

    assert repo.get(created.id).metadata == created.metadata
    assert repo.list_records("TP").errors == ()


def test_objectives_and_entry_and_exit_criteria_are_required(
    repo: MarkdownRepository,
) -> None:
    problems = _problems(repo, objectives=[], entry_criteria=[], exit_criteria=[])

    assert "objectives needs at least one item." in problems
    assert "entry_criteria needs at least one item." in problems
    assert "exit_criteria needs at least one item." in problems


def test_scope_strategy_and_title_are_required(repo: MarkdownRepository) -> None:
    problems = _problems(repo, title=" ", scope="", strategy="")

    assert "title is required." in problems
    assert "scope is required." in problems
    assert "strategy is required." in problems


@pytest.mark.parametrize(
    ("risk", "fragment"),
    [
        (Risk("", "high"), "risk 1 needs a description"),
        (Risk("x", "extreme"), "level 'extreme' is not allowed"),
    ],
)
def test_risks_are_validated(
    repo: MarkdownRepository, risk: Risk, fragment: str
) -> None:
    assert fragment in _problems(repo, risks=[risk])


def test_the_schedule_needs_timezones_and_a_sane_order(
    repo: MarkdownRepository,
) -> None:
    naive = datetime(2026, 3, 1, 9, 0)

    assert "schedule start must be an ISO 8601 timestamp with a timezone" in _problems(
        repo, schedule_start=naive, schedule_end=START
    )
    assert "schedule end cannot be earlier than its start." in _problems(
        repo, schedule_start=START, schedule_end=START - timedelta(hours=1)
    )
    assert "schedule end must be" in _problems(repo, schedule_start=START)


def test_suites_must_be_suite_ids(repo: MarkdownRepository) -> None:
    assert "suites must reference SUITE ids, got TC-001." in _problems(
        repo, suites=["TC-001"]
    )


def test_literal_secrets_in_plan_data_are_refused(repo: MarkdownRepository) -> None:
    problems = _problems(repo, data=["password=hunter2"])

    assert "data contains a literal password value" in problems


def test_an_ai_generated_plan_needs_a_review_before_approval(
    repo: MarkdownRepository,
) -> None:
    plan = create_plan(repo, _draft(origin="ai", generated_by="opencode"))

    with pytest.raises(RecordValidationError, match="cannot be approved without"):
        repo.update(plan.id, {"status": "approved"})
    assert "needs generated_by" in _problems(repo, origin="ai")


def _selection(**overrides: Any) -> list[dict[str, Any]]:
    item: dict[str, Any] = {
        "id": "TC-001",
        "decision": "include",
        "reasons": [{"factor": "criticality", "detail": "marked critical"}],
    }
    item.update(overrides)
    return [item]


def test_a_selection_is_stored_with_its_reasons_and_rendered(
    repo: MarkdownRepository,
) -> None:
    plan = create_plan(repo, _draft())

    updated = set_selection(
        repo,
        plan.id,
        [
            *_selection(),
            {
                "id": "TC-002",
                "decision": "exclude",
                "reasons": [{"factor": "time", "detail": "over the budget"}],
            },
        ],
    )

    assert [i["decision"] for i in updated.metadata["selection"]] == [
        "include",
        "exclude",
    ]
    assert "## Selection and rationale" in updated.body
    assert "### Include TC-001\n- criticality: marked critical" in updated.body
    assert "### Exclude TC-002\n- time: over the budget" in updated.body


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"reasons": []}, "needs at least one reason"),
        ({"reasons": None}, "needs at least one reason"),
        ({"reasons": [{"factor": "vibes", "detail": "x"}]}, "needs a factor from"),
        (
            {"reasons": [{"factor": "time", "detail": " "}]},
            "the time reason needs a detail",
        ),
        ({"decision": "maybe"}, "decision 'maybe' is not allowed"),
        ({"id": "REQ-001"}, "only TC and SUITE can be selected"),
        ({"id": "nope"}, "is not a record id"),
        ({"source": "magic"}, "source 'magic' is not allowed"),
    ],
)
def test_every_inclusion_and_exclusion_must_be_justified_and_valid(
    repo: MarkdownRepository, change: dict[str, Any], fragment: str
) -> None:
    plan = create_plan(repo, _draft())

    with pytest.raises(RecordValidationError, match=fragment):
        set_selection(repo, plan.id, _selection(**change))


def test_a_record_cannot_appear_twice_in_the_selection(
    repo: MarkdownRepository,
) -> None:
    plan = create_plan(repo, _draft())

    with pytest.raises(RecordValidationError, match="appears more than once"):
        set_selection(repo, plan.id, [*_selection(), *_selection(decision="exclude")])


def test_an_invalid_update_leaves_the_plan_untouched(repo: MarkdownRepository) -> None:
    plan = create_plan(repo, _draft())
    before = plan.path.read_text(encoding="utf-8")

    with pytest.raises(RecordValidationError):
        update_plan(repo, plan.id, {"exit_criteria": []})

    assert plan.path.read_text(encoding="utf-8") == before


def test_update_changes_fields_and_rebuilds_the_body(repo: MarkdownRepository) -> None:
    plan = create_plan(repo, _draft())

    updated = update_plan(repo, plan.id, {"status": "in_review", "owners": ["Ana"]})

    assert updated.metadata["status"] == "in_review"
    assert "## Owners\n\n- Ana" in updated.body
