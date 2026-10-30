"""Stable record identifiers (NFR-003).

An id is ``<PREFIX>-<NNN>``: a known prefix and a number starting at 1, padded
to at least three digits. Ids are never reused or renamed.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

ID_PREFIXES: tuple[str, ...] = (
    "PROJ",
    "REQ",
    "ISSUE",
    "TC",
    "EXEC",
    "BUG",
    "SEC",
    "API",
    "REL",
    "EVD",
    "TP",
    "SUITE",
    "PIPE",
    "PIPE-EXEC",
    "COMMENT",
)

_PATTERN = re.compile(r"^(?P<prefix>[A-Z]+(?:-[A-Z]+)*)-(?P<number>\d+)$")


@dataclass(frozen=True)
class RecordId:
    """A parsed identifier."""

    prefix: str
    number: int

    def __str__(self) -> str:
        return f"{self.prefix}-{self.number:03d}"


def parse_id(value: str) -> RecordId:
    """Parse an id, rejecting unknown prefixes and non-canonical numbers."""
    match = _PATTERN.match(value)
    if match is None:
        raise ValueError(f"{value!r} is not an id such as TC-001.")
    prefix = match.group("prefix")
    if prefix not in ID_PREFIXES:
        raise ValueError(
            f"{value!r} has an unknown prefix {prefix!r}. "
            f"Valid prefixes: {', '.join(ID_PREFIXES)}."
        )
    record_id = RecordId(prefix, int(match.group("number")))
    if record_id.number < 1 or str(record_id) != value:
        raise ValueError(
            f"{value!r} is not canonical; expected {prefix}-NNN with a number "
            "from 1 and no extra leading zeros."
        )
    return record_id


def is_valid_id(value: object) -> bool:
    """Whether ``value`` is a well-formed id."""
    if not isinstance(value, str):
        return False
    try:
        parse_id(value)
    except ValueError:
        return False
    return True


def format_id(prefix: str, number: int) -> str:
    """Build an id, validating the prefix and the number."""
    if prefix not in ID_PREFIXES:
        raise ValueError(f"Unknown id prefix {prefix!r}.")
    if number < 1:
        raise ValueError(f"Id numbers start at 1, got {number}.")
    return str(RecordId(prefix, number))


def next_id(prefix: str, existing: Iterable[str]) -> str:
    """Return the next free id for ``prefix``.

    Existing ids with other prefixes or malformed values are ignored. The
    result is always above the highest existing number, so ids are never
    reused after a record is removed from the middle of the sequence.
    """
    numbers = [
        record_id.number
        for value in existing
        if is_valid_id(value) and (record_id := parse_id(value)).prefix == prefix
    ]
    return format_id(prefix, max(numbers, default=0) + 1)
