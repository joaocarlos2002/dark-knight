"""The action guard: scope, approvals, rate limits, and cancellation (REQ-030).

Every risky action goes through :meth:`ActionGuard.authorize` before it happens.
The answer is never "probably fine": the action is allowed by policy, allowed by
a person's approval bound to this exact action, or an exception says why not.
Approvals are single-use, expire, and are bound to the action's fingerprint, so
approving one thing never authorizes another. Everything is written to the audit
log, which is also where approval state lives.
"""

import hashlib
import secrets
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from qa_workbench.security.audit import AuditEntry, AuditLog
from qa_workbench.security.policy import (
    ActionRequest,
    Category,
    requires_approval,
)
from qa_workbench.security.settings import SecuritySettings

APPROVAL_TTL = timedelta(hours=1)


class SecurityError(Exception):
    """Base class for refusals by the guard."""


class ApprovalRequired(SecurityError):
    def __init__(self, request_id: str, action: str, reason: str) -> None:
        super().__init__(
            f"'{action}' needs approval ({reason}). Request {request_id} is pending: "
            f"a person runs `batman security approve {request_id} --by NAME`."
        )
        self.request_id = request_id


class ApprovalDenied(SecurityError):
    def __init__(self, request_id: str, action: str, reason: str) -> None:
        super().__init__(f"'{action}' was denied ({request_id}): {reason}")
        self.request_id = request_id


class ApprovalError(SecurityError):
    """A decision that cannot be recorded (unknown, already decided, no reason)."""


class RateLimitExceeded(SecurityError):
    def __init__(self, host: str, limit: int, retry_after: float) -> None:
        super().__init__(
            f"Rate limit reached for {host}: {limit} requests per minute. "
            f"Retry in {retry_after:.0f}s."
        )
        self.retry_after = retry_after


class Cancelled(SecurityError):
    pass


LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def is_loopback(url: str) -> bool:
    """A web URL on this very machine: always in scope, never external."""
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and (
        (parts.hostname or "").lower() in LOOPBACK_HOSTS
    )


def fingerprint(action: ActionRequest) -> str:
    text = "\n".join(
        (action.action, action.category.value, action.detail, action.target_url)
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Approval:
    request_id: str
    status: str  # pending, approved, denied, used, expired
    action: str
    category: str
    detail: str
    requested_by: str
    decided_by: str = ""
    reason: str = ""
    fingerprint: str = ""


class ApprovalBook:
    """Approval state, derived from the audit log."""

    def __init__(self, audit: AuditLog, clock: Callable[[], datetime] | None = None):
        self._audit = audit
        self._clock = clock or (lambda: datetime.now(UTC))

    def all(self) -> list[Approval]:
        approvals: dict[str, dict] = {}
        for entry in self._audit.entries():
            if entry.kind == "approval_requested":
                approvals[entry.data["request_id"]] = {
                    **entry.data,
                    "status": "pending",
                    "requested_by": entry.actor,
                    "at": entry.time,
                }
            elif entry.kind in ("approval_granted", "approval_denied"):
                item = approvals.get(entry.data["request_id"])
                if item is not None:
                    item["status"] = (
                        "approved" if entry.kind == "approval_granted" else "denied"
                    )
                    item["decided_by"] = entry.actor
                    item["reason"] = entry.data.get("reason", "")
                    item["decided_at"] = entry.time
            elif entry.kind == "approval_used":
                item = approvals.get(entry.data["request_id"])
                if item is not None:
                    item["status"] = "used"
        result = []
        for item in approvals.values():
            status = item["status"]
            decided = item.get("decided_at") or item["at"]
            if status in ("pending", "approved", "denied") and (
                self._clock() - datetime.fromisoformat(decided) > APPROVAL_TTL
            ):
                status = "expired" if status != "denied" else "denied"
            result.append(
                Approval(
                    item["request_id"],
                    status,
                    item["action"],
                    item["category"],
                    item.get("detail", ""),
                    item["requested_by"],
                    item.get("decided_by", ""),
                    item.get("reason", ""),
                    item["fingerprint"],
                )
            )
        return result

    def pending(self) -> list[Approval]:
        return [a for a in self.all() if a.status == "pending"]

    def get(self, request_id: str) -> Approval | None:
        return next((a for a in self.all() if a.request_id == request_id), None)

    def decide(
        self, request_id: str, *, approve: bool, by: str, reason: str = ""
    ) -> None:
        approval = self.get(request_id)
        if approval is None:
            raise ApprovalError(f"There is no approval request {request_id}.")
        if approval.status != "pending":
            raise ApprovalError(
                f"{request_id} is already {approval.status} and cannot be decided."
            )
        if not by.strip():
            raise ApprovalError("A decision needs the name of the person deciding.")
        if by.strip().lower() == approval.requested_by.strip().lower():
            raise ApprovalError(
                f"{by!r} requested this action and cannot also decide it."
            )
        if not approve and not reason.strip():
            raise ApprovalError("A denial needs a reason.")
        self._audit.append(
            "approval_granted" if approve else "approval_denied",
            by.strip(),
            {"request_id": request_id, "reason": reason.strip()},
        )


class RateLimiter:
    """At most N requests per rolling minute and host; over the limit is an error."""

    def __init__(self, per_minute: int, clock: Callable[[], float]) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def acquire(self, url: str) -> None:
        host = (urlsplit(url).hostname or url).lower()
        now = self._clock()
        with self._lock:
            window = self._seen.setdefault(host, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if len(window) >= self._per_minute:
                raise RateLimitExceeded(host, self._per_minute, 60 - (now - window[0]))
            window.append(now)


class ActionGuard:
    def __init__(
        self,
        settings: SecuritySettings,
        audit: AuditLog,
        *,
        clock: Callable[[], float] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        import time

        self.settings = settings
        self.audit = audit
        self.book = ApprovalBook(audit, now)
        self.limiter = RateLimiter(
            settings.max_requests_per_minute, clock or time.monotonic
        )
        self._cancelled = threading.Event()

    def authorize(self, action: ActionRequest) -> None:
        """Return if the action may proceed; otherwise raise a SecurityError."""
        self.check_cancelled()
        category = action.category
        reason = f"{category.value} actions always need approval"
        in_scope = True
        if action.target_url:
            in_scope = self.settings.host_allowed(action.target_url)
            if not in_scope:
                category = Category.OUT_OF_SCOPE
                reason = f"{action.target_url} is outside the authorized hosts"
        if not requires_approval(self.settings.mode, category):
            self.audit.append(
                "action_allowed",
                action.requested_by,
                {
                    "action": action.action,
                    "category": category.value,
                    "detail": action.detail,
                },
            )
            if action.target_url:
                self.limiter.acquire(action.target_url)
            return
        if category is Category.ROUTINE:
            reason = f"mode {self.settings.mode.value} asks before every change"
        self._require_approval(action, category, reason)
        if action.target_url:
            self.limiter.acquire(action.target_url)

    def _require_approval(
        self, action: ActionRequest, category: Category, reason: str
    ) -> None:
        action = ActionRequest(
            action.action,
            category,
            action.detail,
            action.target_url,
            action.requested_by,
        )
        fp = fingerprint(action)
        matching = [a for a in self.book.all() if a.fingerprint == fp]
        for approval in reversed(matching):
            if approval.status == "approved":
                self.audit.append(
                    "approval_used",
                    action.requested_by,
                    {"request_id": approval.request_id, "action": action.action},
                )
                return
            if approval.status == "denied":
                raise ApprovalDenied(
                    approval.request_id, action.action, approval.reason
                )
            if approval.status == "pending":
                raise ApprovalRequired(approval.request_id, action.action, reason)
        request_id = "APR-" + secrets.token_hex(4)
        self.audit.append(
            "approval_requested",
            action.requested_by,
            {
                "request_id": request_id,
                "action": action.action,
                "category": category.value,
                "detail": action.detail,
                "target_url": action.target_url,
                "fingerprint": fp,
                "reason": reason,
            },
        )
        raise ApprovalRequired(request_id, action.action, reason)

    # -- cancellation --------------------------------------------------------

    def cancel(self, by: str, reason: str = "") -> AuditEntry:
        self._cancelled.set()
        return self.audit.append("cancelled", by, {"reason": reason})

    def check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise Cancelled("The run was cancelled; no further action is authorized.")
