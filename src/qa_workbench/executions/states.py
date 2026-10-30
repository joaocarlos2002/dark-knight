"""The execution lifecycle (REQ-018).

    created -> planned -> awaiting_approval -> running
            -> passed | failed | blocked | inconclusive | cancelled
            -> finalized

Approval is only needed for risky executions; a plan that needs none goes from
``planned`` straight to ``running``. An execution can be cancelled until it has
a result. Results are final: ``blocked``, ``inconclusive``, and ``cancelled``
are never turned into ``passed``, and the only way out of a result is
``finalized``. A finalized execution never changes.
"""

from enum import StrEnum


class State(StrEnum):
    CREATED = "created"
    PLANNED = "planned"
    AWAITING_APPROVAL = "awaiting_approval"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"
    FINALIZED = "finalized"


RESULT_STATES = frozenset(
    {
        State.PASSED,
        State.FAILED,
        State.BLOCKED,
        State.INCONCLUSIVE,
        State.CANCELLED,
    }
)
STATUS_NAMES = frozenset(state.value for state in State)
RESULT_NAMES = frozenset(state.value for state in RESULT_STATES)

_TRANSITIONS: dict[State, frozenset[State]] = {
    State.CREATED: frozenset({State.PLANNED, State.CANCELLED}),
    State.PLANNED: frozenset({State.AWAITING_APPROVAL, State.RUNNING, State.CANCELLED}),
    State.AWAITING_APPROVAL: frozenset({State.RUNNING, State.CANCELLED}),
    State.RUNNING: RESULT_STATES,
    State.PASSED: frozenset({State.FINALIZED}),
    State.FAILED: frozenset({State.FINALIZED}),
    State.BLOCKED: frozenset({State.FINALIZED}),
    State.INCONCLUSIVE: frozenset({State.FINALIZED}),
    State.CANCELLED: frozenset({State.FINALIZED}),
    State.FINALIZED: frozenset(),
}


class InvalidTransition(Exception):
    """Raised when a state change is not allowed by the lifecycle."""


def parse_state(value: str) -> State:
    """Parse a state name, listing the valid ones when it is unknown."""
    try:
        return State(value)
    except ValueError:
        names = ", ".join(state.value for state in State)
        raise ValueError(f"Unknown state {value!r}. Valid states: {names}.") from None


def next_states(state: State) -> frozenset[State]:
    """The states an execution can move to from ``state``."""
    return _TRANSITIONS[state]


def validate_transition(
    current: State, target: State, *, requires_approval: bool = False
) -> None:
    """Raise ``InvalidTransition`` unless ``current`` may move to ``target``."""
    if target not in _TRANSITIONS[current]:
        allowed = ", ".join(sorted(s.value for s in _TRANSITIONS[current])) or "none"
        reason = (
            f"{current.value} is final."
            if current is State.FINALIZED
            else f"From {current.value} it can only move to: {allowed}."
        )
        raise InvalidTransition(
            f"Cannot move from {current.value} to {target.value}. {reason}"
        )
    if requires_approval and current is State.PLANNED and target is State.RUNNING:
        raise InvalidTransition(
            "This execution requires approval: move it to awaiting_approval and "
            "have it approved before it runs."
        )
