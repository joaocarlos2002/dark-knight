"""Markdown documents with YAML frontmatter (REQ-006).

A document is UTF-8 text that starts with a ``---`` fence, a YAML mapping, a
closing ``---`` fence, and then a Markdown body::

    ---
    id: TC-001
    created_at: 2026-01-01T10:00:00-03:00
    ---

    # TC-001
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from qa_workbench.storage.errors import FrontmatterError

FENCE = "---"


@dataclass(frozen=True)
class Document:
    """Parsed frontmatter and Markdown body. Line endings are LF."""

    metadata: dict[str, Any]
    body: str


class _Dumper(yaml.SafeDumper):
    """Writes timestamps as ISO 8601 with ``T``, matching the specification."""


def _represent_datetime(dumper: yaml.SafeDumper, value: datetime) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:timestamp", value.isoformat())


def _represent_list(dumper: yaml.SafeDumper, value: list[Any]) -> yaml.Node:
    # Short lists of plain values stay on one line, e.g. ``requirements: [REQ-001]``.
    flat = all(isinstance(item, str | int | float | bool | None) for item in value)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", value, flow_style=flat)


_Dumper.add_representer(datetime, _represent_datetime)
_Dumper.add_representer(list, _represent_list)


def parse_document(text: str, source: Path | str = "<memory>") -> Document:
    """Split and parse a document, raising ``FrontmatterError`` on any problem."""
    if text.startswith("﻿"):
        raise FrontmatterError(
            source, "starts with a byte order mark; save it as UTF-8 without BOM."
        )
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0].rstrip() != FENCE:
        raise FrontmatterError(
            source, "must start with a '---' frontmatter fence on line 1."
        )
    try:
        closing = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip() == FENCE
        )
    except StopIteration:
        raise FrontmatterError(
            source, "the frontmatter is not closed by a '---' line."
        ) from None

    raw = "\n".join(lines[1:closing])
    try:
        metadata = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise FrontmatterError(
            source, f"the frontmatter is not valid YAML: {error}"
        ) from error
    if metadata is None:
        raise FrontmatterError(source, "the frontmatter is empty.")
    if not isinstance(metadata, dict):
        raise FrontmatterError(source, "the frontmatter must be a mapping of fields.")
    bad_keys = [key for key in metadata if not isinstance(key, str)]
    if bad_keys:
        raise FrontmatterError(
            source, f"frontmatter field names must be text, got {bad_keys[0]!r}."
        )

    body_lines = lines[closing + 1 :]
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]
    return Document(metadata, "\n".join(body_lines))


def dump_document(metadata: dict[str, Any], body: str) -> str:
    """Serialize a document with LF line endings and a final newline."""
    try:
        header = yaml.dump(
            metadata,
            Dumper=_Dumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=10_000,
        )
    except yaml.YAMLError as error:
        raise FrontmatterError(
            "<memory>", f"the metadata cannot be serialized: {error}"
        ) from error
    text = f"{FENCE}\n{header}{FENCE}\n"
    body = body.replace("\r\n", "\n").rstrip("\n")
    return f"{text}\n{body}\n" if body else text


def read_document(path: Path) -> Document:
    """Read a UTF-8 file and parse it."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise FrontmatterError(path, f"is not valid UTF-8: {error}") from error
    except OSError as error:
        raise FrontmatterError(path, f"cannot be read: {error}") from error
    return parse_document(text, path)
