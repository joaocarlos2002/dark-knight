from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import (
    ActionGuard,
    ApprovalBook,
    ApprovalDenied,
    ApprovalError,
    ApprovalRequired,
    Cancelled,
    RateLimiter,
    RateLimitExceeded,
)
from qa_workbench.security.policy import ActionRequest, AutonomyMode, Category
from qa_workbench.security.settings import SecuritySettings

STAGING = "https://staging.example.com/api"


def _guard(tmp_path: Path, **settings) -> ActionGuard:
    options = {"allowed_hosts": ("staging.example.com",), **settings}
    return ActionGuard(SecuritySettings(**options), AuditLog(tmp_path))


def _comment(detail: str = "Post result to issue #7") -> ActionRequest:
    return ActionRequest(
        "post comment", Category.EXTERNAL_COMMENT, detail, requested_by="agent"
    )


def _pending_id(guard: ActionGuard, action: ActionRequest) -> str:
    with pytest.raises(ApprovalRequired) as error:
        guard.authorize(action)
    return error.value.request_id


# -- audit log ---------------------------------------------------------------


def test_audit_entries_are_chained_and_verifiable(tmp_path: Path) -> None:
    log = AuditLog(tmp_path)
    log.append("a", "ana", {"x": 1})
    log.append("b", "bob", {"y": 2})

    assert log.verify() == 2
    assert [e.sequence for e in log.entries()] == [1, 2]
    assert log.entries()[1].previous_hash == log.entries()[0].hash


@pytest.mark.parametrize("tamper", ["edit", "delete_first", "reorder"])
def test_any_change_to_the_log_is_detected(tmp_path: Path, tamper: str) -> None:
    log = AuditLog(tmp_path)
    for kind in ("a", "b", "c"):
        log.append(kind, "ana", {})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    if tamper == "edit":
        lines[1] = lines[1].replace('"ana"', '"mallory"')
    elif tamper == "delete_first":
        lines = lines[1:]
    else:
        lines[0], lines[1] = lines[1], lines[0]
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(AuditError, match="changed|not a valid"):
        log.verify()
    with pytest.raises(AuditError):
        log.append("d", "ana", {})  # a damaged log is never extended


def test_secrets_never_reach_the_log(tmp_path: Path) -> None:
    log = AuditLog(tmp_path)

    log.append("x", "ana", {"detail": "used password=hunter22 and ghp_" + "a" * 30})

    text = log.path.read_text(encoding="utf-8")
    assert "hunter22" not in text and "ghp_aaaa" not in text
    assert "[REDACTED]" in text


# -- approvals ----------------------------------------------------------------


def test_a_sensitive_action_asks_then_proceeds_once_approved(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    action = _comment()

    request_id = _pending_id(guard, action)
    assert _pending_id(guard, action) == request_id  # asking again reuses it
    guard.book.decide(request_id, approve=True, by="Ana", reason="looks right")

    guard.authorize(action)  # allowed, and it uses up the approval
    with pytest.raises(ApprovalRequired) as again:
        guard.authorize(action)
    assert again.value.request_id != request_id


def test_an_approval_covers_exactly_one_action(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    request_id = _pending_id(guard, _comment("Post result A"))
    guard.book.decide(request_id, approve=True, by="Ana")

    other = _comment("Post result B")

    assert _pending_id(guard, other) != request_id
    different_category = ActionRequest(
        "post comment", Category.CODE_CHANGE, "Post result A"
    )
    assert _pending_id(guard, different_category) != request_id


def test_denial_blocks_with_the_reason(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    request_id = _pending_id(guard, _comment())
    guard.book.decide(request_id, approve=False, by="Ana", reason="not yet verified")

    with pytest.raises(ApprovalDenied, match="not yet verified"):
        guard.authorize(_comment())


def test_decisions_are_validated(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    request_id = _pending_id(guard, _comment())

    with pytest.raises(ApprovalError, match="no approval request"):
        guard.book.decide("APR-nope", approve=True, by="Ana")
    with pytest.raises(ApprovalError, match="name of the person"):
        guard.book.decide(request_id, approve=True, by="  ")
    with pytest.raises(ApprovalError, match="cannot also decide"):
        guard.book.decide(request_id, approve=True, by="Agent")
    with pytest.raises(ApprovalError, match="needs a reason"):
        guard.book.decide(request_id, approve=False, by="Ana")
    guard.book.decide(request_id, approve=True, by="Ana")
    with pytest.raises(ApprovalError, match="already approved"):
        guard.book.decide(request_id, approve=False, by="Ana", reason="changed my mind")


def test_approvals_expire(tmp_path: Path) -> None:
    now = [datetime(2026, 10, 1, 12, tzinfo=UTC)]
    guard = ActionGuard(
        SecuritySettings(allowed_hosts=("staging.example.com",)),
        AuditLog(tmp_path, lambda: now[0]),
        now=lambda: now[0],
    )
    guard.book = ApprovalBook(guard.audit, lambda: now[0])
    request_id = _pending_id(guard, _comment())
    guard.book.decide(request_id, approve=True, by="Ana")

    now[0] += timedelta(hours=2)

    assert guard.book.get(request_id).status == "expired"  # type: ignore[union-attr]
    assert _pending_id(guard, _comment()) != request_id


def test_every_step_is_in_the_audit_log(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    request_id = _pending_id(guard, _comment())
    guard.book.decide(request_id, approve=True, by="Ana", reason="ok")
    guard.authorize(_comment())

    kinds = [e.kind for e in guard.audit.entries()]
    assert kinds == ["approval_requested", "approval_granted", "approval_used"]
    granted = guard.audit.entries()[1]
    assert granted.actor == "Ana" and granted.data["reason"] == "ok"


# -- modes and scope ------------------------------------------------------------


def test_routine_work_depends_on_the_mode(tmp_path: Path) -> None:
    routine = ActionRequest("create test case", Category.ROUTINE)

    _guard(tmp_path / "a", mode=AutonomyMode.SEMI_AUTONOMOUS).authorize(routine)
    with pytest.raises(ApprovalRequired, match="asks before every change"):
        _guard(tmp_path / "b", mode=AutonomyMode.ASSISTED).authorize(routine)


def test_reads_inside_the_scope_need_nothing(tmp_path: Path) -> None:
    guard = _guard(tmp_path)

    guard.authorize(ActionRequest("fetch page", Category.READ, target_url=STAGING))

    assert guard.audit.entries()[-1].kind == "action_allowed"


def test_a_host_outside_the_scope_needs_approval_even_to_read(tmp_path: Path) -> None:
    guard = _guard(tmp_path)

    with pytest.raises(ApprovalRequired, match="outside the authorized hosts"):
        guard.authorize(
            ActionRequest("fetch", Category.READ, target_url="https://prod.example.com")
        )


def test_without_configured_hosts_every_external_host_is_out_of_scope(
    tmp_path: Path,
) -> None:
    guard = ActionGuard(SecuritySettings(), AuditLog(tmp_path))

    with pytest.raises(ApprovalRequired):
        guard.authorize(ActionRequest("fetch", Category.READ, target_url=STAGING))


# -- limits and cancellation -----------------------------------------------------


def test_rate_limit_is_an_error_with_a_retry_time() -> None:
    now = [0.0]
    limiter = RateLimiter(2, lambda: now[0])

    limiter.acquire("https://a.test/x")
    limiter.acquire("https://a.test/y")
    with pytest.raises(RateLimitExceeded, match="2 requests per minute") as error:
        limiter.acquire("https://a.test/z")
    assert 0 < error.value.retry_after <= 60

    limiter.acquire("https://b.test/")  # another host has its own budget
    now[0] = 61
    limiter.acquire("https://a.test/x")


def test_the_guard_applies_the_rate_limit(tmp_path: Path) -> None:
    guard = _guard(tmp_path, max_requests_per_minute=1)
    read = ActionRequest("fetch", Category.READ, target_url=STAGING)

    guard.authorize(read)
    with pytest.raises(RateLimitExceeded):
        guard.authorize(read)


def test_cancelling_stops_every_later_action_and_is_recorded(tmp_path: Path) -> None:
    guard = _guard(tmp_path)

    entry = guard.cancel("Ana", "wrong environment")

    assert entry.kind == "cancelled" and entry.actor == "Ana"
    with pytest.raises(Cancelled):
        guard.authorize(ActionRequest("fetch", Category.READ, target_url=STAGING))
