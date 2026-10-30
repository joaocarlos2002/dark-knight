"""Sanitization of requests and responses before they are persisted (REQ-025).

Everything the API runner records goes through a :class:`Sanitizer`. It works on
three levels so a credential is caught even when its name gives nothing away:

* by **name**: sensitive headers, query parameters, and JSON keys are replaced
  whole (``Authorization``, ``Cookie``, ``password``, ``access_token`` ...);
* by **value**: every secret the run itself used or extracted (a token read
  from the environment, a value captured from a login response) is replaced
  wherever it appears, including inside free text;
* by **shape**: bearer tokens, JWTs, cloud keys, private keys, and
  ``password=...`` assignments are recognized in any text.

Personal data (e-mail addresses and CPF numbers) is masked by default. Bodies
are truncated, never persisted whole.
"""

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"
TRUNCATED = "[truncated]"
DEFAULT_MAX_BODY = 4000
_MIN_SECRET_LENGTH = 4

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-xsrf-token",
    }
)
_SENSITIVE_NAME = re.compile(
    r"(?i)pass(?:word|wd)?|secret|token|api[_-]?key|auth|credential|session|"
    r"cookie|private[_-]?key|\bssn\b|\bcpf\b"
)
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]*"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)",
        re.S,
    ),
)
_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization)\b([\"']?\s*[:=]\s*[\"']?)([^\s,;\"'&]+)"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")


class Sanitizer:
    """Removes credentials and personal data from what is about to be saved."""

    def __init__(
        self,
        secrets: Iterable[str] = (),
        *,
        mask_personal_data: bool = True,
        max_body: int = DEFAULT_MAX_BODY,
    ) -> None:
        self._secrets: set[str] = set()
        self._mask_personal = mask_personal_data
        self._max_body = max_body
        for value in secrets:
            self.add_secret(value)

    def add_secret(self, value: str) -> None:
        """Remember a value that must never appear in saved output."""
        if len(value) >= _MIN_SECRET_LENGTH:
            self._secrets.add(value)

    def headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        return {
            name: REDACTED
            if name.lower() in SENSITIVE_HEADERS or _SENSITIVE_NAME.search(name)
            else self.text(value)
            for name, value in headers.items()
        }

    def url(self, url: str) -> str:
        """Hide user info and credential-looking query values."""
        parts = urlsplit(url)
        host = parts.netloc.rpartition("@")[2]
        query = urlencode(
            [
                (name, REDACTED if _SENSITIVE_NAME.search(name) else self.text(value))
                for name, value in parse_qsl(parts.query, keep_blank_values=True)
            ],
            safe="[]",
        )
        return self.text(urlunsplit(parts._replace(netloc=host, query=query)))

    def params(self, params: Mapping[str, Any]) -> dict[str, Any]:
        return {
            name: REDACTED if _SENSITIVE_NAME.search(name) else self.text(str(value))
            for name, value in params.items()
        }

    def value(self, data: Any) -> Any:
        """Sanitize parsed JSON: sensitive keys whole, every string by value."""
        if isinstance(data, dict):
            return {
                key: REDACTED if _SENSITIVE_NAME.search(str(key)) else self.value(item)
                for key, item in data.items()
            }
        if isinstance(data, list):
            return [self.value(item) for item in data]
        if isinstance(data, str):
            return self.text(data)
        return data

    def text(self, text: str) -> str:
        """Sanitize free text."""
        for secret in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(secret, REDACTED)
        for pattern in _PATTERNS:
            text = pattern.sub(REDACTED, text)
        text = _ASSIGNMENT.sub(
            lambda m: (
                m.group(0)
                if m.group(3).startswith(("[", "$", "<", "{"))
                else f"{m.group(1)}{m.group(2)}{REDACTED}"
            ),
            text,
        )
        if self._mask_personal:
            text = _EMAIL.sub("[email]", text)
            text = _CPF.sub("[cpf]", text)
        return text

    def body(self, raw: bytes | str | None) -> str:
        """Sanitize a request or response body into saveable text."""
        if raw is None or raw == b"" or raw == "":
            return ""
        text = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        try:
            rendered = json.dumps(
                self.value(json.loads(text)), indent=2, ensure_ascii=False
            )
        except ValueError:
            rendered = self.text(text)
        if len(rendered) > self._max_body:
            rendered = rendered[: self._max_body] + f"\n{TRUNCATED}"
        return rendered
