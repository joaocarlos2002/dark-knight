"""Test design techniques (REQ-012).

Each technique is a validated model of the information the technique needs,
plus a function that derives the test conditions from it. Models reject
inconsistent input instead of repairing it.
"""

from enum import StrEnum
from itertools import product
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Technique(StrEnum):
    """The supported design techniques."""

    EQUIVALENCE_PARTITIONING = "equivalence_partitioning"
    BOUNDARY_VALUE_ANALYSIS = "boundary_value_analysis"
    DECISION_TABLE = "decision_table"
    STATE_TRANSITION = "state_transition"
    USE_CASE = "use_case"
    EXPLORATORY = "exploratory"


TECHNIQUE_NAMES = tuple(technique.value for technique in Technique)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Condition(BaseModel):
    """A test condition derived from a technique."""

    label: str
    value: str
    valid: bool


class Partition(_Model):
    name: Text
    valid: bool
    examples: list[Text] = Field(min_length=1)


class EquivalencePartitioning(_Model):
    """Partition the input domain; test one representative per partition."""

    subject: Text
    partitions: list[Partition] = Field(min_length=2)

    @model_validator(mode="after")
    def _has_valid_and_invalid(self) -> "EquivalencePartitioning":
        if not any(p.valid for p in self.partitions):
            raise ValueError("needs at least one valid partition")
        if not any(not p.valid for p in self.partitions):
            raise ValueError("needs at least one invalid partition")
        names = [p.name.lower() for p in self.partitions]
        if len(names) != len(set(names)):
            raise ValueError("partition names must be unique")
        return self

    def derive(self) -> list[Condition]:
        return [
            Condition(label=p.name, value=p.examples[0], valid=p.valid)
            for p in self.partitions
        ]


class BoundaryValueAnalysis(_Model):
    """Test at and around the edges of a numeric range."""

    subject: Text
    minimum: int
    maximum: int
    three_value: bool = False

    @model_validator(mode="after")
    def _ordered(self) -> "BoundaryValueAnalysis":
        if self.minimum > self.maximum:
            raise ValueError("minimum cannot be greater than maximum")
        return self

    def derive(self) -> list[Condition]:
        low, high = self.minimum, self.maximum
        points = {low - 1: False, low: True, high: True, high + 1: False}
        if self.three_value:
            points.update({low + 1: low + 1 <= high, high - 1: high - 1 >= low})
        return [
            Condition(label=f"{self.subject} = {value}", value=str(value), valid=valid)
            for value, valid in sorted(points.items())
        ]


class DecisionRule(_Model):
    """One column of a decision table; unmentioned conditions are "don't care"."""

    when: dict[Text, bool]
    then: Text


class DecisionTable(_Model):
    """Every combination of conditions must lead to exactly one action."""

    conditions: list[Text] = Field(min_length=1, max_length=8)
    rules: list[DecisionRule] = Field(min_length=1)

    @model_validator(mode="after")
    def _complete_and_consistent(self) -> "DecisionTable":
        if len({c.lower() for c in self.conditions}) != len(self.conditions):
            raise ValueError("conditions must be unique")
        known = set(self.conditions)
        for rule in self.rules:
            unknown = sorted(set(rule.when) - known)
            if unknown:
                raise ValueError(f"a rule uses unknown conditions: {unknown}")
        table: dict[tuple[bool, ...], str] = {}
        for rule in self.rules:
            for combo in self._expand(rule):
                if table.get(combo, rule.then) != rule.then:
                    raise ValueError(
                        f"conflicting actions {table[combo]!r} and {rule.then!r} "
                        f"for {self._describe(combo)}"
                    )
                table[combo] = rule.then
        missing = [
            combo
            for combo in product([True, False], repeat=len(self.conditions))
            if combo not in table
        ]
        if missing:
            shown = "; ".join(self._describe(combo) for combo in missing[:3])
            more = f" (and {len(missing) - 3} more)" if len(missing) > 3 else ""
            raise ValueError(f"the rules do not cover: {shown}{more}")
        return self

    def _expand(self, rule: DecisionRule) -> list[tuple[bool, ...]]:
        options = [
            [rule.when[c]] if c in rule.when else [True, False] for c in self.conditions
        ]
        return list(product(*options))

    def _describe(self, combo: tuple[bool, ...]) -> str:
        return ", ".join(
            f"{name}={'yes' if value else 'no'}"
            for name, value in zip(self.conditions, combo, strict=True)
        )

    def derive(self) -> list[Condition]:
        """One condition per full combination, with the action it must produce."""
        table: dict[tuple[bool, ...], str] = {}
        for rule in self.rules:
            for combo in self._expand(rule):
                table[combo] = rule.then
        return [
            Condition(label=self._describe(combo), value=table[combo], valid=True)
            for combo in product([True, False], repeat=len(self.conditions))
        ]


class Transition(_Model):
    source: Text
    event: Text
    target: Text


class StateTransition(_Model):
    """A finite state model; test every valid transition and try the invalid ones."""

    states: list[Text] = Field(min_length=2)
    initial: Text
    transitions: list[Transition] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> "StateTransition":
        states = set(self.states)
        if len(states) != len(self.states):
            raise ValueError("states must be unique")
        if self.initial not in states:
            raise ValueError(f"the initial state {self.initial!r} is not a state")
        seen: dict[tuple[str, str], str] = {}
        for item in self.transitions:
            for state in (item.source, item.target):
                if state not in states:
                    raise ValueError(f"the transition uses unknown state {state!r}")
            key = (item.source, item.event)
            if seen.get(key, item.target) != item.target:
                raise ValueError(
                    f"{item.event!r} from {item.source!r} leads to two different states"
                )
            seen[key] = item.target
        return self

    def unreachable_states(self) -> list[str]:
        reached = {self.initial}
        changed = True
        while changed:
            changed = False
            for item in self.transitions:
                if item.source in reached and item.target not in reached:
                    reached.add(item.target)
                    changed = True
        return [state for state in self.states if state not in reached]

    def derive(self) -> list[Condition]:
        """Valid transitions to take, and undefined state/event pairs to refuse."""
        conditions = [
            Condition(
                label=f"{t.source} --{t.event}--> {t.target}",
                value=t.target,
                valid=True,
            )
            for t in self.transitions
        ]
        defined = {(t.source, t.event) for t in self.transitions}
        events = sorted({t.event for t in self.transitions})
        conditions.extend(
            Condition(
                label=f"{state} --{event}--> (not allowed)", value=state, valid=False
            )
            for state in self.states
            for event in events
            if (state, event) not in defined
        )
        return conditions


class AlternateFlow(_Model):
    at_step: int = Field(ge=1)
    condition: Text
    steps: list[Text] = Field(min_length=1)
    rejoins: bool = False


class UseCase(_Model):
    """A main flow with alternate flows that branch from it."""

    name: Text
    actor: Text
    main_flow: list[Text] = Field(min_length=1)
    alternates: list[AlternateFlow] = []

    @model_validator(mode="after")
    def _steps_exist(self) -> "UseCase":
        for alternate in self.alternates:
            if alternate.at_step > len(self.main_flow):
                raise ValueError(
                    f"an alternate flow branches at step {alternate.at_step}, but the "
                    f"main flow has {len(self.main_flow)} steps"
                )
        return self

    def derive(self) -> list[Condition]:
        """One scenario for the main flow and one for each alternate flow."""
        scenarios = [
            Condition(label="Main flow", value=" > ".join(self.main_flow), valid=True)
        ]
        for alternate in self.alternates:
            steps = self.main_flow[: alternate.at_step - 1] + alternate.steps
            if alternate.rejoins:
                steps += self.main_flow[alternate.at_step :]
            scenarios.append(
                Condition(
                    label=f"At step {alternate.at_step}: {alternate.condition}",
                    value=" > ".join(steps),
                    valid=True,
                )
            )
        return scenarios


class Charter(_Model):
    """An exploratory testing charter: mission, time box, and areas to explore."""

    mission: Text
    timebox_minutes: int = Field(ge=1, le=480)
    areas: list[Text] = []

    def derive(self) -> list[Condition]:
        return [
            Condition(label=area, value=self.mission, valid=True) for area in self.areas
        ]


_MODELS: dict[str, type[BaseModel]] = {
    Technique.EQUIVALENCE_PARTITIONING.value: EquivalencePartitioning,
    Technique.BOUNDARY_VALUE_ANALYSIS.value: BoundaryValueAnalysis,
    Technique.DECISION_TABLE.value: DecisionTable,
    Technique.STATE_TRANSITION.value: StateTransition,
    Technique.USE_CASE.value: UseCase,
    Technique.EXPLORATORY.value: Charter,
}


def parse_technique(name: str, data: object) -> BaseModel:
    """Validate the data of one technique, raising ``ValueError`` with the reasons."""
    model = _MODELS.get(name)
    if model is None:
        raise ValueError(
            f"unknown technique {name!r}; use one of: {', '.join(TECHNIQUE_NAMES)}"
        )
    try:
        return model.model_validate(data)
    except ValidationError as error:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in item['loc']) or 'data'}: {item['msg']}"
            for item in error.errors()
        )
        raise ValueError(f"{name}: {detail}") from error
