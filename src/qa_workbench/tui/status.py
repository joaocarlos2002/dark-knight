"""Status vocabulary shown in the TUI.

Every status has a name and a symbol, so meaning never depends on color alone.
"""

from dataclasses import dataclass
from enum import Enum


class Status(Enum):
    """Execution and activity states."""

    PASSED = "passed"
    FAILED = "failed"
    RUNNING = "running"
    PENDING = "pending"
    WARNING = "warning"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    AI = "ai"
    READY = "ready"


@dataclass(frozen=True)
class StatusStyle:
    """Presentation of one status."""

    symbol: str
    label: str
    tone: str


_STYLES: dict[Status, StatusStyle] = {
    Status.PASSED: StatusStyle("✓", "PASSED", "success"),
    Status.FAILED: StatusStyle("✗", "FAILED", "error"),
    Status.RUNNING: StatusStyle("●", "RUNNING", "info"),
    Status.PENDING: StatusStyle("◷", "PENDING", "warning"),
    Status.WARNING: StatusStyle("▲", "WARNING", "warning"),
    Status.BLOCKED: StatusStyle("⊘", "BLOCKED", "warning"),
    Status.INCONCLUSIVE: StatusStyle("?", "INCONCLUSIVE", "muted"),
    Status.CANCELLED: StatusStyle("■", "CANCELLED", "muted"),
    Status.SKIPPED: StatusStyle("–", "SKIPPED", "muted"),
    Status.AI: StatusStyle("✦", "AI PROCESSING", "ai"),
    Status.READY: StatusStyle("●", "READY", "success"),
}


def style_for(status: Status) -> StatusStyle:
    """Return the presentation for a status."""
    try:
        return _STYLES[status]
    except KeyError as error:
        raise ValueError(f"No presentation defined for status {status!r}.") from error


def parse_status(value: str) -> Status:
    """Parse a status name, rejecting unknown values."""
    try:
        return Status(value.strip().lower())
    except ValueError as error:
        known = ", ".join(status.value for status in Status)
        raise ValueError(
            f"Unknown status {value!r}. Expected one of: {known}."
        ) from error


def format_status(status: Status) -> str:
    """Render a status as ``<symbol> <LABEL>``."""
    style = style_for(status)
    return f"{style.symbol} {style.label}"
