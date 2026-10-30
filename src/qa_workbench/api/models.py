"""Definitions and results of API tests (REQ-024)."""

from dataclasses import dataclass, field
from typing import Any

METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
AUTH_KINDS = frozenset({"none", "bearer", "basic", "header"})


@dataclass(frozen=True)
class AuthSpec:
    """How to authenticate. Credentials are named, never stored: ``env`` is the
    name of an environment variable that holds the value at run time."""

    kind: str = "none"
    env: str = ""
    user_env: str = ""
    header: str = ""


@dataclass(frozen=True)
class Expectation:
    """What a correct response looks like. Every given rule is checked."""

    status: tuple[int, ...] = ()
    max_ms: float | None = None
    json_schema: dict[str, Any] | None = None
    json_equals: dict[str, Any] = field(default_factory=dict)
    contains: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Extract:
    """A value to carry to later steps, read with a ``$.a.b[0]`` path."""

    path: str
    secret: bool = False


@dataclass(frozen=True)
class ApiStep:
    name: str
    method: str
    url: str
    path_params: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    json: Any = None
    body: str | None = None
    auth: AuthSpec = field(default_factory=AuthSpec)
    expect: Expectation = field(default_factory=Expectation)
    extract: dict[str, Extract] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiDefinition:
    """One test: a base URL and steps run in order (a flow when chained)."""

    name: str
    base_url: str
    steps: tuple[ApiStep, ...]
    timeout_seconds: float = 30.0
    stop_on_failure: bool = True


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class Exchange:
    """A request and its response, already sanitized."""

    method: str
    url: str
    request_headers: dict[str, str]
    request_body: str
    status: int | None
    response_headers: dict[str, str]
    response_body: str
    elapsed_ms: float | None


PASSED, FAILED, ERROR, SKIPPED = "passed", "failed", "error", "skipped"


@dataclass(frozen=True)
class StepResult:
    """``failed``: the API answered but not as expected. ``error``: the step
    could not run (bad definition, missing credential, no connection)."""

    name: str
    status: str
    checks: tuple[CheckResult, ...] = ()
    exchange: Exchange | None = None
    error: str = ""


@dataclass(frozen=True)
class FlowResult:
    name: str
    base_url: str
    steps: tuple[StepResult, ...]

    @property
    def status(self) -> str:
        statuses = {step.status for step in self.steps}
        if ERROR in statuses:
            return ERROR
        if FAILED in statuses:
            return FAILED
        return PASSED
