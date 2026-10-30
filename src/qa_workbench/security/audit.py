"""Append-only, tamper-evident audit log (REQ-030, NFR-005).

One JSON object per line in ``<project>/security/audit.jsonl``. Every entry
carries the SHA-256 of the previous one, so editing, reordering, or removing an
entry is found by :meth:`AuditLog.verify`. Text is passed through
``redact_secrets`` before it is written: the log records what was decided and
by whom, never a credential.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qa_workbench.core.secrets import redact_secrets
from qa_workbench.security.settings import SECURITY_DIRECTORY

AUDIT_FILE = "audit.jsonl"
GENESIS = "0" * 64


class AuditError(Exception):
    """The audit log is damaged or cannot be written."""


@dataclass(frozen=True)
class AuditEntry:
    sequence: int
    time: str
    kind: str
    actor: str
    data: dict[str, Any]
    previous_hash: str
    hash: str


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


def _digest(
    sequence: int, time: str, kind: str, actor: str, data: Any, previous: str
) -> str:
    payload = json.dumps(
        [sequence, time, kind, actor, data, previous],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(
        self, project_root: Path, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.path = project_root / SECURITY_DIRECTORY / AUDIT_FILE

    def entries(self) -> list[AuditEntry]:
        """Every entry, verified in order; raises :class:`AuditError` if damaged."""
        if not self.path.is_file():
            return []
        entries: list[AuditEntry] = []
        previous = GENESIS
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            try:
                raw = json.loads(line)
                entry = AuditEntry(**raw)
            except (ValueError, TypeError) as error:
                raise AuditError(
                    f"{self.path} line {number} is not a valid entry"
                ) from error
            expected = _digest(
                entry.sequence,
                entry.time,
                entry.kind,
                entry.actor,
                entry.data,
                previous,
            )
            if (
                entry.sequence != number
                or entry.previous_hash != previous
                or entry.hash != expected
            ):
                raise AuditError(
                    f"{self.path} was changed: entry {number} does not match its "
                    "hash chain"
                )
            entries.append(entry)
            previous = entry.hash
        return entries

    def append(self, kind: str, actor: str, data: dict[str, Any]) -> AuditEntry:
        entries = self.entries()  # refuses to extend a damaged log
        previous = entries[-1].hash if entries else GENESIS
        sequence = len(entries) + 1
        time = self._clock().isoformat(timespec="seconds")
        clean = _clean(data)
        entry = AuditEntry(
            sequence,
            time,
            kind,
            _clean(actor),
            clean,
            previous,
            _digest(sequence, time, kind, _clean(actor), clean, previous),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.__dict__, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
        return entry

    def verify(self) -> int:
        """Number of entries if the chain is intact; raises otherwise."""
        return len(self.entries())
