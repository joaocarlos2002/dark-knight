"""Detect literal secrets before they are written to records (NFR-005).

This is deliberately stricter than log redaction: it flags a value only when it
looks like an actual credential (an assignment of a literal to a secret-like
name, or a well-known token format). Prose such as "enter the password" and
placeholders such as ``$PASSWORD`` or ``<password>`` are fine.
"""

import re

_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization)\b[\"']?\s*[:=]\s*[\"']?([^\s,;\"']+)"
)
_PLACEHOLDER = re.compile(r"^(?:[$<{%\[(]|\*+$|x{3,}$|\.{3}$)", re.IGNORECASE)
_KNOWN_FORMATS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a JSON Web Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.")),
    ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("a GitLab token", re.compile(r"glpat-[A-Za-z0-9_-]{16,}")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
)


def find_secrets(text: str) -> list[str]:
    """Describe each literal secret found in ``text``; empty when there is none."""
    found: list[str] = []
    for match in _ASSIGNMENT.finditer(text):
        value = match.group(2)
        if not _PLACEHOLDER.match(value):
            found.append(f"a literal {match.group(1).lower()} value")
    for description, pattern in _KNOWN_FORMATS:
        if pattern.search(text):
            found.append(description)
    return found


def redact_secrets(text: str) -> str:
    """Replace literal secrets in ``text`` (the counterpart of ``find_secrets``).

    Used before showing text from outside, such as a CI job log, which may print
    a credential by mistake.
    """

    def assignment(match: re.Match[str]) -> str:
        value = match.group(2)
        if _PLACEHOLDER.match(value):
            return match.group(0)
        return match.group(0).replace(value, "[REDACTED]")

    text = _ASSIGNMENT.sub(assignment, text)
    for _, pattern in _KNOWN_FORMATS:
        text = pattern.sub("[REDACTED]", text)
    return text
