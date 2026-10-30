"""Parse requirements from Markdown or plain text (REQ-009).

Markdown: each ``##`` section is one requirement. A document with no ``##``
section but a ``#`` heading is one requirement. Plain text: each block of text
separated by blank lines is one requirement, and its first line is the title.

Inside a requirement, leading ``Key: value`` lines set ``Priority``, ``Status``,
``Tags``, and ``Author`` (Portuguese names also work). Acceptance criteria are
the list under an ``Acceptance criteria`` label or ``###`` heading
(``Critérios de aceitação``). Everything else is the description.

Nothing is guessed: a value that is not understood is reported, not replaced.
"""

import re
from dataclasses import dataclass, field

from qa_workbench.requirements.schema import PRIORITIES, STATUSES

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_KEY_LINE = re.compile(r"^\s*([A-Za-zÀ-ÿ ]+?)\s*:\s*(.+?)\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.*\S)\s*$")
_CRITERIA_LABEL = re.compile(
    r"^\s*(?:#{1,6}\s*)?(acceptance criteria|crit[eé]rios? de aceita[cç][aã]o|"
    r"criteria|crit[eé]rios)\s*:?\s*$",
    re.IGNORECASE,
)

_KEYS = {
    "priority": "priority",
    "prioridade": "priority",
    "status": "status",
    "tags": "tags",
    "etiquetas": "tags",
    "author": "author",
    "autor": "author",
}
_PRIORITY_ALIASES = {
    "alta": "high",
    "media": "medium",
    "média": "medium",
    "baixa": "low",
}
_STATUS_ALIASES = {
    "rascunho": "draft",
    "em revisão": "in_review",
    "em revisao": "in_review",
    "aprovado": "approved",
    "rejeitado": "rejected",
    "obsoleto": "obsolete",
}
MAX_TITLE = 200


@dataclass(frozen=True)
class ParsedRequirement:
    """One requirement found in a source, before it becomes a record."""

    title: str
    description: str
    line: int
    priority: str | None = None
    status: str | None = None
    tags: tuple[str, ...] = ()
    author: str | None = None
    acceptance_criteria: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseIssue:
    """A problem found while reading a source."""

    line: int
    message: str


@dataclass
class ParseResult:
    requirements: list[ParsedRequirement] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)


def _normalize_choice(
    value: str, aliases: dict[str, str], allowed: tuple[str, ...] | frozenset[str]
) -> str | None:
    lowered = value.strip().lower()
    cleaned = aliases.get(lowered, lowered.replace(" ", "_"))
    return cleaned if cleaned in allowed else None


def _parse_section(
    title: str, lines: list[str], first_line: int
) -> tuple[ParsedRequirement | None, list[ParseIssue]]:
    issues: list[ParseIssue] = []
    where = first_line
    if not title.strip():
        return None, [ParseIssue(where, "the requirement has no title.")]
    if len(title) > MAX_TITLE:
        return None, [
            ParseIssue(where, f"the title is longer than {MAX_TITLE} characters.")
        ]

    fields: dict[str, str] = {}
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    while index < len(lines):
        match = _KEY_LINE.match(lines[index])
        key = _KEYS.get(match.group(1).strip().lower()) if match else None
        if match is None or key is None:
            break
        fields[key] = match.group(2)
        index += 1
    rest = lines[index:]

    criteria: list[str] = []
    description: list[str] = []
    in_criteria = False
    in_fence = False
    for text in rest:
        if _FENCE.match(text):
            in_fence = not in_fence
        if not in_fence and _CRITERIA_LABEL.match(text):
            in_criteria = True
            continue
        if in_criteria and not in_fence:
            item = _LIST_ITEM.match(text)
            if item:
                criteria.append(item.group(1))
                continue
            if not text.strip():
                continue
            in_criteria = False
        description.append(text)

    priority = status = None
    if "priority" in fields:
        priority = _normalize_choice(fields["priority"], _PRIORITY_ALIASES, PRIORITIES)
        if priority is None:
            issues.append(
                ParseIssue(
                    where,
                    f"priority {fields['priority']!r} is not understood; use "
                    f"{', '.join(PRIORITIES)}.",
                )
            )
    if "status" in fields:
        status = _normalize_choice(fields["status"], _STATUS_ALIASES, STATUSES)
        if status is None:
            issues.append(
                ParseIssue(
                    where,
                    f"status {fields['status']!r} is not understood; use "
                    f"{', '.join(sorted(STATUSES))}.",
                )
            )
    if issues:
        return None, issues

    tags = tuple(
        tag.strip() for tag in re.split(r"[,;]", fields.get("tags", "")) if tag.strip()
    )
    return (
        ParsedRequirement(
            title=title.strip(),
            description="\n".join(description).strip(),
            line=first_line,
            priority=priority,
            status=status,
            tags=tags,
            author=fields.get("author", "").strip() or None,
            acceptance_criteria=tuple(criteria),
        ),
        [],
    )


def parse_markdown(text: str) -> ParseResult:
    """Read requirements from a Markdown document."""
    lines = text.replace("\r\n", "\n").split("\n")
    headings: list[tuple[int, int, str]] = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _HEADING.match(line)
        if match:
            headings.append((number, len(match.group(1)), match.group(2)))

    # A "## Acceptance criteria" heading belongs to a requirement; it does not
    # start one.
    candidates = [
        h for h in headings if not _CRITERIA_LABEL.match("#" * h[1] + " " + h[2])
    ]
    level = 2 if any(h[1] == 2 for h in candidates) else 1
    starts = [h for h in candidates if h[1] == level]
    result = ParseResult()
    if not starts:
        result.issues.append(
            ParseIssue(1, "no requirement found; use one '## Title' per requirement.")
        )
        return result

    for position, (number, _, title) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines)
        body = lines[number:end]
        parsed, issues = _parse_section(title, body, number)
        result.issues.extend(issues)
        if parsed is not None:
            result.requirements.append(parsed)
    return result


def parse_text(text: str) -> ParseResult:
    """Read requirements from plain text: one block per requirement."""
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] = []
    start = 1
    for number, line in enumerate(lines, start=1):
        if line.strip():
            if not current:
                start = number
            current.append(line)
        elif current:
            blocks.append((start, current))
            current = []
    if current:
        blocks.append((start, current))

    result = ParseResult()
    if not blocks:
        result.issues.append(ParseIssue(1, "the text has no requirement."))
        return result
    for number, block in blocks:
        parsed, issues = _parse_section(block[0].strip(), block[1:], number)
        result.issues.extend(issues)
        if parsed is not None:
            result.requirements.append(parsed)
    return result
