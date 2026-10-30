from typing import Any

import pytest

from qa_workbench.testcases.techniques import (
    TECHNIQUE_NAMES,
    BoundaryValueAnalysis,
    Charter,
    DecisionTable,
    EquivalencePartitioning,
    StateTransition,
    UseCase,
    parse_technique,
)


def _labels(conditions) -> list[tuple[str, str, bool]]:
    return [(c.label, c.value, c.valid) for c in conditions]


def test_all_six_techniques_are_supported() -> None:
    assert TECHNIQUE_NAMES == (
        "equivalence_partitioning",
        "boundary_value_analysis",
        "decision_table",
        "state_transition",
        "use_case",
        "exploratory",
    )


# --- equivalence partitioning ------------------------------------------------


def _partitions(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "subject": "Age",
        "partitions": [
            {"name": "adult", "valid": True, "examples": ["30", "45"]},
            {"name": "minor", "valid": False, "examples": ["10"]},
            {"name": "not a number", "valid": False, "examples": ["abc"]},
        ],
    }
    data.update(overrides)
    return data


def test_one_representative_is_taken_from_each_partition() -> None:
    model = EquivalencePartitioning.model_validate(_partitions())

    assert _labels(model.derive()) == [
        ("adult", "30", True),
        ("minor", "10", False),
        ("not a number", "abc", False),
    ]


@pytest.mark.parametrize(
    ("partitions", "message"),
    [
        ([{"name": "a", "valid": True, "examples": ["1"]}], "at least 2"),
        (
            [
                {"name": "a", "valid": True, "examples": ["1"]},
                {"name": "b", "valid": True, "examples": ["2"]},
            ],
            "at least one invalid partition",
        ),
        (
            [
                {"name": "a", "valid": False, "examples": ["1"]},
                {"name": "b", "valid": False, "examples": ["2"]},
            ],
            "at least one valid partition",
        ),
        (
            [
                {"name": "a", "valid": True, "examples": ["1"]},
                {"name": "A", "valid": False, "examples": ["2"]},
            ],
            "must be unique",
        ),
        (
            [
                {"name": "a", "valid": True, "examples": []},
                {"name": "b", "valid": False, "examples": ["2"]},
            ],
            "at least 1",
        ),
    ],
)
def test_inconsistent_partitions_are_rejected(
    partitions: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_technique("equivalence_partitioning", _partitions(partitions=partitions))


# --- boundary value analysis -------------------------------------------------


def test_two_value_boundaries() -> None:
    model = BoundaryValueAnalysis(subject="Age", minimum=18, maximum=65)

    assert _labels(model.derive()) == [
        ("Age = 17", "17", False),
        ("Age = 18", "18", True),
        ("Age = 65", "65", True),
        ("Age = 66", "66", False),
    ]


def test_three_value_boundaries_add_the_inner_neighbours() -> None:
    model = BoundaryValueAnalysis(
        subject="Age", minimum=18, maximum=65, three_value=True
    )

    values = [(c.value, c.valid) for c in model.derive()]

    assert values == [
        ("17", False),
        ("18", True),
        ("19", True),
        ("64", True),
        ("65", True),
        ("66", False),
    ]


def test_a_single_value_range_has_no_valid_inner_neighbours() -> None:
    model = BoundaryValueAnalysis(subject="Qty", minimum=5, maximum=5, three_value=True)

    assert [(c.value, c.valid) for c in model.derive()] == [
        ("4", False),
        ("5", True),
        ("6", False),
    ]


def test_boundaries_need_an_ordered_range() -> None:
    with pytest.raises(ValueError, match="minimum cannot be greater than maximum"):
        parse_technique(
            "boundary_value_analysis", {"subject": "x", "minimum": 5, "maximum": 1}
        )


# --- decision table ----------------------------------------------------------


def _table(rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {"conditions": ["Registered", "Correct password"], "rules": rules}


FULL_RULES = [
    {"when": {"Registered": True, "Correct password": True}, "then": "log in"},
    {"when": {"Registered": True, "Correct password": False}, "then": "show error"},
    {"when": {"Registered": False}, "then": "offer sign-up"},
]


def test_a_complete_table_derives_one_condition_per_combination() -> None:
    model = DecisionTable.model_validate(_table(FULL_RULES))

    assert _labels(model.derive()) == [
        ("Registered=yes, Correct password=yes", "log in", True),
        ("Registered=yes, Correct password=no", "show error", True),
        ("Registered=no, Correct password=yes", "offer sign-up", True),
        ("Registered=no, Correct password=no", "offer sign-up", True),
    ]


def test_missing_combinations_are_reported() -> None:
    with pytest.raises(ValueError, match="the rules do not cover") as error:
        parse_technique("decision_table", _table(FULL_RULES[:1]))

    assert "Registered=yes, Correct password=no" in str(error.value)
    assert "Registered=no, Correct password=no" in str(error.value)


def test_conflicting_rules_are_reported() -> None:
    rules = [*FULL_RULES, {"when": {"Registered": False}, "then": "block"}]

    with pytest.raises(ValueError, match="conflicting actions"):
        parse_technique("decision_table", _table(rules))


def test_unknown_conditions_are_reported() -> None:
    rules = [{"when": {"Admin": True}, "then": "x"}]

    with pytest.raises(ValueError, match="unknown conditions"):
        parse_technique("decision_table", _table(rules))


def test_the_same_action_twice_is_not_a_conflict() -> None:
    rules = [
        {"when": {"Registered": True}, "then": "ok"},
        {"when": {"Registered": True, "Correct password": True}, "then": "ok"},
        {"when": {"Registered": False}, "then": "no"},
    ]

    assert parse_technique("decision_table", _table(rules)) is not None


def test_too_many_conditions_are_refused() -> None:
    with pytest.raises(ValueError, match="at most 8"):
        parse_technique(
            "decision_table",
            {
                "conditions": [f"c{i}" for i in range(9)],
                "rules": [{"when": {}, "then": "x"}],
            },
        )


# --- state transition --------------------------------------------------------

STATES: dict[str, Any] = {
    "states": ["Created", "Running", "Finalized", "Orphan"],
    "initial": "Created",
    "transitions": [
        {"source": "Created", "event": "start", "target": "Running"},
        {"source": "Running", "event": "finish", "target": "Finalized"},
    ],
}


def test_valid_and_invalid_transitions_are_derived() -> None:
    model = StateTransition.model_validate(STATES)

    derived = _labels(model.derive())

    assert derived[:2] == [
        ("Created --start--> Running", "Running", True),
        ("Running --finish--> Finalized", "Finalized", True),
    ]
    assert ("Created --finish--> (not allowed)", "Created", False) in derived
    assert ("Finalized --start--> (not allowed)", "Finalized", False) in derived
    assert len(derived) == 2 + (4 * 2 - 2)


def test_unreachable_states_are_found() -> None:
    assert StateTransition.model_validate(STATES).unreachable_states() == ["Orphan"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"initial": "Nowhere"}, "is not a state"),
        ({"states": ["A", "A"]}, "must be unique"),
        (
            {"transitions": [{"source": "Created", "event": "x", "target": "Gone"}]},
            "unknown state 'Gone'",
        ),
        (
            {
                "transitions": [
                    {"source": "Created", "event": "go", "target": "Running"},
                    {"source": "Created", "event": "go", "target": "Finalized"},
                ]
            },
            "two different states",
        ),
    ],
)
def test_inconsistent_state_models_are_rejected(
    change: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_technique("state_transition", {**STATES, **change})


# --- use case ----------------------------------------------------------------

USE_CASE: dict[str, Any] = {
    "name": "Withdraw cash",
    "actor": "Customer",
    "main_flow": ["Insert card", "Enter PIN", "Choose amount", "Take cash"],
    "alternates": [
        {"at_step": 2, "condition": "PIN is wrong", "steps": ["Show error"]},
        {
            "at_step": 3,
            "condition": "Balance is low",
            "steps": ["Offer a smaller amount"],
            "rejoins": True,
        },
    ],
}


def test_scenarios_come_from_the_main_and_alternate_flows() -> None:
    model = UseCase.model_validate(USE_CASE)

    assert _labels(model.derive()) == [
        ("Main flow", "Insert card > Enter PIN > Choose amount > Take cash", True),
        ("At step 2: PIN is wrong", "Insert card > Show error", True),
        (
            "At step 3: Balance is low",
            "Insert card > Enter PIN > Offer a smaller amount > Take cash",
            True,
        ),
    ]


def test_an_alternate_cannot_branch_after_the_main_flow_ends() -> None:
    bad = {**USE_CASE, "alternates": [{"at_step": 9, "condition": "x", "steps": ["y"]}]}

    with pytest.raises(ValueError, match="branches at step 9"):
        parse_technique("use_case", bad)


# --- exploratory -------------------------------------------------------------


def test_a_charter_needs_a_mission_and_a_sane_time_box() -> None:
    charter = Charter(mission="Explore checkout", timebox_minutes=60, areas=["Cart"])

    assert _labels(charter.derive()) == [("Cart", "Explore checkout", True)]
    with pytest.raises(ValueError, match="less than or equal to 480"):
        parse_technique("exploratory", {"mission": "x", "timebox_minutes": 600})
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        parse_technique("exploratory", {"mission": "x", "timebox_minutes": 0})


# --- parsing -----------------------------------------------------------------


def test_unknown_techniques_list_the_valid_ones() -> None:
    with pytest.raises(ValueError, match="unknown technique 'guessing'") as error:
        parse_technique("guessing", {})

    assert "decision_table" in str(error.value)


def test_errors_name_the_technique_and_the_field() -> None:
    with pytest.raises(ValueError, match=r"boundary_value_analysis: minimum:"):
        parse_technique("boundary_value_analysis", {"subject": "x", "maximum": 1})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        parse_technique(
            "exploratory", {"mission": "x", "timebox_minutes": 5, "surprise": 1}
        )


def test_long_lists_of_missing_combinations_are_summarized() -> None:
    data = {
        "conditions": ["A", "B", "C"],
        "rules": [{"when": {"A": True, "B": True, "C": True}, "then": "x"}],
    }

    with pytest.raises(ValueError, match=r"\(and 4 more\)"):
        parse_technique("decision_table", data)
