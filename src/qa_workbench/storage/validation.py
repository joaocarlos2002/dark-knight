"""Validation of record frontmatter and relative links (REQ-007, NFR-003)."""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

from qa_workbench.storage.ids import ID_PREFIXES, parse_id

BASE_REQUIRED: tuple[str, ...] = ("id", "status", "created_at", "updated_at")


@dataclass(frozen=True)
class RecordSchema:
    """The rules for one kind of record.

    ``statuses`` is the closed set of allowed ``status`` values.
    ``required`` lists fields beyond ``BASE_REQUIRED``.
    ``immutable_statuses`` are final statuses: once a record reaches one, it is
    sealed and can only be corrected through history events.
    ``optional_timestamps`` are timestamp fields that may be empty, such as
    ``finished_at``. ``references`` maps a field holding one id or a list of ids
    to the prefixes those ids may have. ``choices`` maps a field to the closed
    set of values it may hold (when present). ``text_lists`` are fields that, when
    present, must be lists of non-empty text. ``extra_checks`` are functions that
    take the metadata and return problems, for rules a schema cannot express
    declaratively.
    """

    prefix: str
    directory: str
    statuses: frozenset[str]
    required: tuple[str, ...] = ()
    optional_timestamps: tuple[str, ...] = ()
    immutable_statuses: frozenset[str] = frozenset()
    references: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    choices: Mapping[str, frozenset[str]] = field(default_factory=dict)
    text_lists: tuple[str, ...] = ()
    extra_checks: tuple[Callable[[Mapping[str, Any]], list[str]], ...] = ()

    def __post_init__(self) -> None:
        if self.prefix not in ID_PREFIXES:
            raise ValueError(f"Unknown id prefix {self.prefix!r}.")
        folder = PurePosixPath(self.directory)
        if not self.directory or folder.is_absolute() or ".." in folder.parts:
            raise ValueError(
                f"Schema directory must be a relative folder, got {self.directory!r}."
            )
        if not self.statuses:
            raise ValueError("A schema needs at least one status.")
        unknown_final = self.immutable_statuses - self.statuses
        if unknown_final:
            raise ValueError(
                "immutable_statuses must be allowed statuses, got "
                f"{sorted(unknown_final)}."
            )
        for field_name, prefixes in self.references.items():
            unknown = [p for p in prefixes if p not in ID_PREFIXES]
            if unknown:
                raise ValueError(
                    f"Reference {field_name!r} uses unknown prefixes: {unknown}."
                )


def _describe(value: Any) -> str:
    if isinstance(value, datetime):
        return "a timestamp without a timezone"
    if isinstance(value, date):
        return "a date without a time or timezone"
    return f"{type(value).__name__} {value!r}"


def _check_timestamp(name: str, value: Any, problems: list[str]) -> datetime | None:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value
    if isinstance(value, str):
        problems.append(
            f"{name} must be an ISO 8601 timestamp with a timezone such as "
            f"2026-01-01T10:00:00-03:00 (written without quotes), got text {value!r}."
        )
    else:
        problems.append(
            f"{name} must be an ISO 8601 timestamp with a timezone such as "
            f"2026-01-01T10:00:00-03:00, got {_describe(value)}."
        )
    return None


def _check_references(
    name: str, value: Any, prefixes: tuple[str, ...], problems: list[str]
) -> None:
    if value is None:
        return
    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, str):
            problems.append(f"{name} must contain ids, got {_describe(item)}.")
            continue
        try:
            record_id = parse_id(item)
        except ValueError as error:
            problems.append(f"{name}: {error}")
            continue
        if record_id.prefix not in prefixes:
            problems.append(
                f"{name} must reference {' or '.join(prefixes)} ids, got {item}."
            )


def validate_metadata(
    schema: RecordSchema,
    metadata: Mapping[str, Any],
    *,
    expected_id: str | None = None,
) -> list[str]:
    """Return every problem found in ``metadata``; an empty list means valid."""
    problems: list[str] = []

    for name in (*BASE_REQUIRED, *schema.required):
        value = metadata.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{name} is required.")

    record_id = metadata.get("id")
    if isinstance(record_id, str) and record_id.strip():
        try:
            parsed = parse_id(record_id)
        except ValueError as error:
            problems.append(f"id: {error}")
        else:
            if parsed.prefix != schema.prefix:
                problems.append(
                    f"id must start with {schema.prefix}-, got {record_id}."
                )
            elif expected_id is not None and record_id != expected_id:
                problems.append(
                    f"id {record_id} does not match its file name {expected_id}."
                )
    elif record_id is not None and not isinstance(record_id, str):
        problems.append(f"id must be text, got {_describe(record_id)}.")

    status = metadata.get("status")
    if isinstance(status, str) and status.strip() and status not in schema.statuses:
        problems.append(
            f"status {status!r} is not allowed; use one of: "
            f"{', '.join(sorted(schema.statuses))}."
        )
    elif status is not None and not isinstance(status, str):
        problems.append(f"status must be text, got {_describe(status)}.")

    created = updated = None
    if metadata.get("created_at") is not None:
        created = _check_timestamp("created_at", metadata["created_at"], problems)
    if metadata.get("updated_at") is not None:
        updated = _check_timestamp("updated_at", metadata["updated_at"], problems)
    if created is not None and updated is not None and updated < created:
        problems.append("updated_at cannot be earlier than created_at.")
    for name in schema.optional_timestamps:
        if metadata.get(name) is not None:
            _check_timestamp(name, metadata[name], problems)

    for name, prefixes in schema.references.items():
        _check_references(name, metadata.get(name), prefixes, problems)

    for name, allowed in schema.choices.items():
        value = metadata.get(name)
        if value is not None and value not in allowed:
            problems.append(
                f"{name} {value!r} is not allowed; use one of: "
                f"{', '.join(sorted(allowed))}."
            )

    for name in schema.text_lists:
        value = metadata.get(name)
        if value is None:
            continue
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            problems.append(f"{name} must be a list of non-empty text.")

    for check in schema.extra_checks:
        problems.extend(check(metadata))

    return problems


_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_EXTERNAL_SCHEMES = ("http:", "https:", "mailto:")
_INLINE_CODE = re.compile(r"`[^`]*`")


def _links_in(body: str) -> list[tuple[int, str]]:
    """Return ``(line number, target)`` for Markdown links outside code."""
    found: list[tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(body.split("\n"), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _LINK.finditer(_INLINE_CODE.sub("", line)):
            found.append((number, match.group(1)))
    return found


def validate_links(body: str, *, document: Path, root: Path) -> list[str]:
    """Check that relative Markdown links stay inside ``root`` and exist.

    Anchors and ``http``, ``https``, and ``mailto`` links are left alone.
    Obsidian ``[[wikilinks]]`` are allowed but not checked.
    """
    problems: list[str] = []
    base = document.parent
    for line, target in _links_in(body):
        lowered = target.lower()
        if target.startswith("#") or lowered.startswith(_EXTERNAL_SCHEMES):
            continue
        if _SCHEME.match(target) or target.startswith(("/", "\\")):
            problems.append(
                f"line {line}: link {target!r} is absolute; use a relative path."
            )
            continue
        path_part = unquote(re.split(r"[#?]", target, maxsplit=1)[0])
        if not path_part:
            continue
        resolved = (base / path_part).resolve()
        if not resolved.is_relative_to(root.resolve()):
            problems.append(
                f"line {line}: link {target!r} points outside the project folder."
            )
        elif not resolved.exists():
            problems.append(f"line {line}: link {target!r} points to a missing file.")
    return problems
