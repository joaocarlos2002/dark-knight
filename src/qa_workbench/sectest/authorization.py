"""Explicit, scoped, expiring authorization for security tests (REQ-031).

Security checks run only when a person has granted an authorization naming the
hosts, the checks, and an expiry, *and* the host is also in the project's
security settings (two independent gates). The authorization is a file the
person controls; granting and revoking are audited, and an expired or missing
authorization refuses every check instead of falling back to a default.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from qa_workbench.security.audit import AuditLog
from qa_workbench.security.settings import SECURITY_DIRECTORY, SecuritySettings
from qa_workbench.storage.atomic import write_text_atomic

AUTHORIZATION_FILE = "test-authorization.yaml"
MAX_DAYS = 30


class NotAuthorized(Exception):
    """A security check is outside what a person authorized."""


@dataclass(frozen=True)
class SecurityAuthorization:
    authorized_by: str
    purpose: str
    hosts: tuple[str, ...]
    checks: tuple[str, ...]
    granted_at: datetime
    expires_at: datetime

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at


def path_of(project_root: Path) -> Path:
    return project_root / SECURITY_DIRECTORY / AUTHORIZATION_FILE


def grant(
    project_root: Path,
    *,
    authorized_by: str,
    purpose: str,
    hosts: tuple[str, ...],
    checks: tuple[str, ...],
    known_checks: frozenset[str],
    days: float,
    now: datetime | None = None,
) -> SecurityAuthorization:
    """Write an authorization. Every problem is reported together."""
    now = now or datetime.now(UTC)
    problems = []
    if not authorized_by.strip():
        problems.append("say who authorizes the tests")
    if not purpose.strip():
        problems.append("say what the tests are for")
    if not hosts:
        problems.append("name at least one host")
    for host in hosts:
        if not host or any(c in host for c in "*/: ") or host.startswith("."):
            problems.append(f"host {host!r} must be one exact host name")
    if not checks:
        problems.append("name at least one check")
    unknown = sorted(set(checks) - known_checks)
    if unknown:
        problems.append(
            f"unknown check(s): {', '.join(unknown)} "
            f"(available: {', '.join(sorted(known_checks))})"
        )
    if not 0 < days <= MAX_DAYS:
        problems.append(f"validity must be more than 0 and at most {MAX_DAYS} days")
    if problems:
        raise NotAuthorized("The authorization is not valid: " + "; ".join(problems))
    authorization = SecurityAuthorization(
        authorized_by.strip(),
        purpose.strip(),
        tuple(h.lower() for h in hosts),
        tuple(sorted(set(checks))),
        now,
        now + timedelta(days=days),
    )
    path = path_of(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(
        path,
        yaml.safe_dump(
            {
                "authorized_by": authorization.authorized_by,
                "purpose": authorization.purpose,
                "hosts": list(authorization.hosts),
                "checks": list(authorization.checks),
                "granted_at": authorization.granted_at.isoformat(timespec="seconds"),
                "expires_at": authorization.expires_at.isoformat(timespec="seconds"),
            },
            sort_keys=False,
        ),
    )
    AuditLog(project_root).append(
        "security_tests_authorized",
        authorization.authorized_by,
        {
            "hosts": list(authorization.hosts),
            "checks": list(authorization.checks),
            "expires_at": authorization.expires_at.isoformat(timespec="seconds"),
            "purpose": authorization.purpose,
        },
    )
    return authorization


def load(project_root: Path) -> SecurityAuthorization | None:
    """The current authorization; ``None`` when none was ever granted."""
    path = path_of(project_root)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return SecurityAuthorization(
            str(data["authorized_by"]),
            str(data["purpose"]),
            tuple(data["hosts"]),
            tuple(data["checks"]),
            datetime.fromisoformat(data["granted_at"]),
            datetime.fromisoformat(data["expires_at"]),
        )
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as error:
        raise NotAuthorized(
            f"{path} is damaged ({error}); revoke it and grant a new one."
        ) from error


def revoke(project_root: Path, *, by: str, now: datetime | None = None) -> bool:
    path = path_of(project_root)
    if not by.strip():
        raise NotAuthorized("Say who is revoking the authorization.")
    if not path.is_file():
        return False
    path.unlink()
    AuditLog(project_root).append("security_tests_revoked", by.strip(), {})
    return True


def require(
    authorization: SecurityAuthorization | None,
    settings: SecuritySettings,
    url: str,
    check: str,
    *,
    now: datetime | None = None,
) -> None:
    """Raise :class:`NotAuthorized` unless ``check`` on ``url`` is authorized."""
    now = now or datetime.now(UTC)
    host = (urlsplit(url).hostname or "").lower()
    if authorization is None:
        raise NotAuthorized(
            "No security-test authorization exists. A person must run "
            "`batman security-tests authorize` first."
        )
    if authorization.expired(now):
        raise NotAuthorized(
            f"The authorization by {authorization.authorized_by} expired at "
            f"{authorization.expires_at.isoformat(timespec='minutes')}."
        )
    if host not in authorization.hosts:
        raise NotAuthorized(
            f"{host or url!r} is not in the authorized hosts "
            f"({', '.join(authorization.hosts)})."
        )
    if not settings.host_allowed(url):
        raise NotAuthorized(
            f"{host} is authorized for tests but not in the project's allowed hosts "
            "(`batman security set --allow-host`)."
        )
    if check not in authorization.checks:
        raise NotAuthorized(f"The check {check!r} was not authorized.")
