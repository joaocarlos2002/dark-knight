"""Per-project security settings: scope, limits, and mode (spec section 8)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from qa_workbench.security.policy import DEFAULT_MODE, AutonomyMode
from qa_workbench.storage.atomic import write_text_atomic

SECURITY_DIRECTORY = "security"
SETTINGS_FILE = "settings.yaml"


class SecuritySettingsError(ValueError):
    """The settings file or a value in it is invalid."""


@dataclass(frozen=True)
class SecuritySettings:
    """Everything outside these bounds needs approval or is refused.

    ``allowed_hosts`` entries are exact hosts (``staging.example.com``) or a
    leading-dot suffix (``.example.com``); there are no wildcards, so "everything"
    cannot be written by accident.
    """

    mode: AutonomyMode = DEFAULT_MODE
    authorized_environments: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    max_requests_per_minute: int = 60
    timeout_seconds: float = 30.0
    max_retries: int = 0
    data_policy: str = "sanitize-before-persist"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        problems = []
        for host in self.allowed_hosts:
            bare = host.removeprefix(".")
            if not bare or "*" in host or "/" in host or ":" in host or " " in host:
                problems.append(
                    f"allowed host {host!r} must be a host name or a '.suffix' "
                    "without wildcards, paths, or ports"
                )
        if self.max_requests_per_minute < 1:
            problems.append("max_requests_per_minute must be at least 1")
        if self.timeout_seconds <= 0:
            problems.append("timeout_seconds must be positive")
        if self.max_retries < 0:
            problems.append("max_retries cannot be negative")
        if problems:
            raise SecuritySettingsError("; ".join(problems))

    def host_allowed(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        if not host:
            return False
        for allowed in (h.lower() for h in self.allowed_hosts):
            if allowed.startswith("."):
                if host.endswith(allowed) and host != allowed[1:]:
                    return True
            elif host == allowed:
                return True
        return False


def settings_path(project_root: Path) -> Path:
    return project_root / SECURITY_DIRECTORY / SETTINGS_FILE


def load_settings(project_root: Path) -> SecuritySettings:
    """Read the settings; a missing file means the safe defaults, a bad one fails."""
    path = settings_path(project_root)
    if not path.is_file():
        return SecuritySettings()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise SecuritySettingsError(f"Cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise SecuritySettingsError(f"{path} must contain a mapping.")
    try:
        mode = AutonomyMode(data.get("mode", DEFAULT_MODE.value))
    except ValueError as error:
        valid = ", ".join(m.value for m in AutonomyMode)
        raise SecuritySettingsError(
            f"{path}: mode must be one of {valid}; got {data.get('mode')!r}."
        ) from error
    known = {
        "mode",
        "authorized_environments",
        "allowed_hosts",
        "max_requests_per_minute",
        "timeout_seconds",
        "max_retries",
        "data_policy",
    }
    unknown = sorted(set(data) - known)
    if unknown:
        raise SecuritySettingsError(
            f"{path}: unknown setting(s): {', '.join(unknown)}."
        )
    try:
        return SecuritySettings(
            mode=mode,
            authorized_environments=tuple(
                map(str, data.get("authorized_environments", ()))
            ),
            allowed_hosts=tuple(map(str, data.get("allowed_hosts", ()))),
            max_requests_per_minute=int(data.get("max_requests_per_minute", 60)),
            timeout_seconds=float(data.get("timeout_seconds", 30)),
            max_retries=int(data.get("max_retries", 0)),
            data_policy=str(data.get("data_policy", "sanitize-before-persist")),
        )
    except (TypeError, ValueError) as error:
        raise SecuritySettingsError(f"{path}: {error}") from error


def save_settings(project_root: Path, settings: SecuritySettings) -> None:
    path = settings_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "mode": settings.mode.value,
        "authorized_environments": list(settings.authorized_environments),
        "allowed_hosts": list(settings.allowed_hosts),
        "max_requests_per_minute": settings.max_requests_per_minute,
        "timeout_seconds": settings.timeout_seconds,
        "max_retries": settings.max_retries,
        "data_policy": settings.data_policy,
    }
    write_text_atomic(path, yaml.safe_dump(data, sort_keys=False))
