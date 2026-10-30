import pytest

from qa_workbench.executions.states import (
    RESULT_STATES,
    InvalidTransition,
    State,
    next_states,
    parse_state,
    validate_transition,
)

ALLOWED = {
    ("created", "planned"),
    ("created", "cancelled"),
    ("planned", "awaiting_approval"),
    ("planned", "running"),
    ("planned", "cancelled"),
    ("awaiting_approval", "running"),
    ("awaiting_approval", "cancelled"),
    ("running", "passed"),
    ("running", "failed"),
    ("running", "blocked"),
    ("running", "inconclusive"),
    ("running", "cancelled"),
    ("passed", "finalized"),
    ("failed", "finalized"),
    ("blocked", "finalized"),
    ("inconclusive", "finalized"),
    ("cancelled", "finalized"),
}


@pytest.mark.parametrize(
    ("source", "target"),
    [(s.value, t.value) for s in State for t in State],
)
def test_exactly_the_specified_transitions_are_allowed(
    source: str, target: str
) -> None:
    if (source, target) in ALLOWED:
        validate_transition(State(source), State(target))
    else:
        with pytest.raises(InvalidTransition, match="Cannot move from"):
            validate_transition(State(source), State(target))


def test_the_five_results_are_the_ones_in_the_specification() -> None:
    assert {s.value for s in RESULT_STATES} == {
        "passed",
        "failed",
        "blocked",
        "inconclusive",
        "cancelled",
    }


@pytest.mark.parametrize("state", ["blocked", "inconclusive", "cancelled"])
def test_a_non_result_is_never_turned_into_a_pass(state: str) -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(State(state), State.PASSED)


@pytest.mark.parametrize("result", sorted(s.value for s in RESULT_STATES))
def test_a_result_can_only_be_finalized(result: str) -> None:
    assert next_states(State(result)) == {State.FINALIZED}


def test_a_finalized_execution_has_nowhere_to_go() -> None:
    assert next_states(State.FINALIZED) == frozenset()
    with pytest.raises(InvalidTransition, match="finalized is final"):
        validate_transition(State.FINALIZED, State.RUNNING)


def test_the_error_lists_where_it_can_go() -> None:
    with pytest.raises(InvalidTransition) as error:
        validate_transition(State.CREATED, State.RUNNING)

    assert "it can only move to: cancelled, planned" in str(error.value)


def test_an_execution_that_needs_approval_cannot_skip_it() -> None:
    with pytest.raises(InvalidTransition, match="requires approval"):
        validate_transition(State.PLANNED, State.RUNNING, requires_approval=True)

    validate_transition(State.PLANNED, State.AWAITING_APPROVAL, requires_approval=True)
    validate_transition(State.AWAITING_APPROVAL, State.RUNNING, requires_approval=True)


def test_without_the_approval_requirement_planning_can_start_directly() -> None:
    validate_transition(State.PLANNED, State.RUNNING, requires_approval=False)


def test_cancelling_is_possible_until_there_is_a_result() -> None:
    for state in (State.CREATED, State.PLANNED, State.AWAITING_APPROVAL, State.RUNNING):
        validate_transition(state, State.CANCELLED)


@pytest.mark.parametrize("name", [s.value for s in State])
def test_state_names_parse(name: str) -> None:
    assert parse_state(name).value == name


def test_unknown_state_names_list_the_valid_ones() -> None:
    with pytest.raises(ValueError, match="Unknown state 'done'") as error:
        parse_state("done")

    assert "awaiting_approval" in str(error.value)
