"""Running authorized security checks through the action guard (REQ-031).

Before anything is sent, *every* requested check is verified against the
authorization (hosts, checks, expiry) and the project's allowed hosts, so a run
is all-or-nothing: it never sends half of what was asked. Each request then goes
through the guard (scope, rate limit, cancellation) and each check is written
to the audit log. A target that cannot be reached is an ``error`` outcome, not
an empty result.
"""

from dataclasses import dataclass
from datetime import datetime

from qa_workbench.integrations.http import (
    GatewayError,
    GatewayRequest,
    GatewayResponse,
    HttpGateway,
)
from qa_workbench.sectest.authorization import (
    NotAuthorized,
    SecurityAuthorization,
    require,
)
from qa_workbench.sectest.checks import CHECKS, CheckOutcome, Probe
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.policy import ActionRequest, Category

ACTOR = "security-tests"


class GuardedGateway:
    """A GET-only gateway whose every request is authorized by the guard."""

    def __init__(self, inner: HttpGateway, guard: ActionGuard, check: str) -> None:
        self._inner = inner
        self._guard = guard
        self._check = check

    def get(self, request: GatewayRequest) -> GatewayResponse:
        self._guard.authorize(
            ActionRequest(
                f"security check {self._check}",
                Category.READ,
                f"GET {request.url}",
                target_url=request.url,
                requested_by=ACTOR,
            )
        )
        return self._inner.get(request)

    def post(self, request: GatewayRequest) -> GatewayResponse:  # pragma: no cover
        raise NotAuthorized("Security checks never send anything but GET requests.")


@dataclass(frozen=True)
class CheckRun:
    check: str
    status: str  # "completed" or "error"
    outcome: CheckOutcome | None = None
    error: str = ""


@dataclass(frozen=True)
class SecurityRun:
    url: str
    authorized_by: str
    checks: tuple[CheckRun, ...]

    @property
    def findings(self):
        return [f for run in self.checks if run.outcome for f in run.outcome.findings]

    @property
    def ok(self) -> bool:
        return all(run.status == "completed" for run in self.checks)


def run_checks(
    *,
    url: str,
    checks: tuple[str, ...],
    gateway: HttpGateway,
    authorization: SecurityAuthorization | None,
    guard: ActionGuard,
    protected_paths: tuple[str, ...] = (),
    now: datetime | None = None,
) -> SecurityRun:
    unknown = sorted(set(checks) - set(CHECKS))
    if unknown:
        raise NotAuthorized(
            f"Unknown check(s): {', '.join(unknown)}. Available: {', '.join(CHECKS)}."
        )
    for check in checks:  # all-or-nothing, before the first request
        require(authorization, guard.settings, url, check, now=now)
        for path in protected_paths if check == "unauthenticated-access" else ():
            require(authorization, guard.settings, _join(url, path), check, now=now)
    assert authorization is not None

    runs = []
    for check in checks:
        guard.audit.append(
            "security_check_started", ACTOR, {"check": check, "url": url}
        )
        probe = Probe(
            GuardedGateway(gateway, guard, check),  # type: ignore[arg-type]
            url,
            protected_paths,
        )
        try:
            outcome = CHECKS[check](probe)
            run = CheckRun(check, "completed", outcome)
            result = {"requests": outcome.requests, "findings": len(outcome.findings)}
        except GatewayError as error:
            run = CheckRun(check, "error", None, f"could not complete: {error}")
            result = {"error": str(error)}
        guard.audit.append("security_check_finished", ACTOR, {"check": check, **result})
        runs.append(run)
    return SecurityRun(url, authorization.authorized_by, tuple(runs))


def _join(url: str, path: str) -> str:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/{path.lstrip('/')}"
