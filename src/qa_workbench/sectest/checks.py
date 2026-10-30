"""Passive, non-destructive security checks (REQ-031, spec 5.14).

Every check is a plain GET (no payloads, no credentials, no state change) whose
result is read from the response. A finding is *confirmed* only when it is
directly observed in a response ("the header is absent", "the cookie has no
HttpOnly flag"); anything inferred is a *hypothesis* and says what would settle
it. The checks run, not their absence of findings, are what is reported: a clean
run never claims the target is secure.

References to the OWASP lists are informational pointers. This module does not
certify anything, and it does not perform intrusive testing.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from qa_workbench.integrations.http import GatewayRequest, GatewayResponse, HttpGateway

PROBE_ORIGIN = "https://qa-probe.invalid"
SESSION_NAMES = ("sess", "sid", "auth", "token", "jwt", "login")


@dataclass(frozen=True)
class SecurityFinding:
    check: str
    title: str
    severity: str  # high, medium, low, info
    confirmed: bool  # False: a hypothesis
    detail: str
    reference: str = ""


@dataclass(frozen=True)
class CheckOutcome:
    check: str
    requests: int
    findings: tuple[SecurityFinding, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class Probe:
    """What a check may use: a way to GET and the target."""

    gateway: HttpGateway
    url: str
    protected_paths: tuple[str, ...] = ()
    timeout: float = 15.0
    sent: list[str] = field(default_factory=list)

    def get(
        self, url: str, headers: Mapping[str, str] | None = None
    ) -> GatewayResponse:
        self.sent.append(url)
        return self.gateway.get(
            GatewayRequest(url, dict(headers or {}), timeout_seconds=self.timeout)
        )


def _headers(response: GatewayResponse) -> dict[str, str]:
    return {name.lower(): value for name, value in response.headers.items()}


def check_headers(probe: Probe) -> CheckOutcome:
    headers = _headers(probe.get(probe.url))
    findings = []
    rules = [
        ("content-security-policy", "No Content-Security-Policy header", "medium",
         "A05 Security Misconfiguration"),
        ("x-content-type-options", "No X-Content-Type-Options header", "low",
         "A05 Security Misconfiguration"),
        ("referrer-policy", "No Referrer-Policy header", "low",
         "A05 Security Misconfiguration"),
    ]  # fmt: skip
    for header, title, severity, reference in rules:
        if header not in headers:
            findings.append(
                SecurityFinding("headers", title, severity, True,
                                f"The response has no {header} header.", reference)
            )  # fmt: skip
    if "x-frame-options" not in headers and "frame-ancestors" not in headers.get(
        "content-security-policy", ""
    ):
        findings.append(
            SecurityFinding(
                "headers", "Clickjacking protection missing", "medium", True,
                "Neither X-Frame-Options nor CSP frame-ancestors is present.",
                "A05 Security Misconfiguration",
            )
        )  # fmt: skip
    if (
        urlsplit(probe.url).scheme == "https"
        and "strict-transport-security" not in headers
    ):
        findings.append(
            SecurityFinding(
                "headers", "No Strict-Transport-Security header", "medium", True,
                "An HTTPS response without HSTS.", "A02 Cryptographic Failures",
            )
        )  # fmt: skip
    return CheckOutcome("headers", 1, tuple(findings))


def check_info_disclosure(probe: Probe) -> CheckOutcome:
    headers = _headers(probe.get(probe.url))
    findings = []
    server = headers.get("server", "")
    if any(c.isdigit() for c in server) and "/" in server:
        findings.append(
            SecurityFinding(
                "info-disclosure", "Server header exposes a version", "low", True,
                f"Server: {server}", "A05 Security Misconfiguration",
            )
        )  # fmt: skip
    for header in ("x-powered-by", "x-aspnet-version", "x-aspnetmvc-version"):
        if header in headers:
            findings.append(
                SecurityFinding(
                    "info-disclosure", f"{header} exposes the technology", "low", True,
                    f"{header}: {headers[header]}", "A05 Security Misconfiguration",
                )
            )  # fmt: skip
    return CheckOutcome("info-disclosure", 1, tuple(findings))


def check_cookies(probe: Probe) -> CheckOutcome:
    response = probe.get(probe.url)
    raw = [v for k, v in _set_cookie_values(response)]
    if not raw:
        return CheckOutcome("cookies", 1, (), "The response sets no cookies.")
    https = urlsplit(probe.url).scheme == "https"
    findings = []
    for line in raw:
        cookie = SimpleCookie()
        cookie.load(line)
        for name, morsel in cookie.items():
            session_like = any(part in name.lower() for part in SESSION_NAMES)
            flags = [
                ("secure", https, "no Secure flag", "medium"),
                ("httponly", True, "no HttpOnly flag", "medium"),
                ("samesite", True, "no SameSite attribute", "low"),
            ]
            for key, applies, text, severity in flags:
                if applies and not morsel[key]:
                    findings.append(
                        SecurityFinding(
                            "cookies", f"Cookie '{name}' has {text}",
                            severity if session_like else "low", session_like,
                            f"Observed in Set-Cookie for '{name}' (value not recorded)."
                            + ("" if session_like else " The name does not look like a "
                               "session cookie, so the impact is a hypothesis."),
                            "A07 Identification and Authentication Failures",
                        )
                    )  # fmt: skip
    return CheckOutcome("cookies", 1, tuple(findings))


_COOKIE_SPLIT = re.compile(r",\s*(?=[^;,=\s]+=)")


def _set_cookie_values(response: GatewayResponse) -> list[tuple[str, str]]:
    """Each Set-Cookie line. The gateway joins repeated headers with ", ", so they
    are split again where a new ``name=`` starts (a date's comma does not)."""
    found = []
    for name, value in response.headers.items():
        if name.lower() == "set-cookie":
            found += [(name, part) for part in _COOKIE_SPLIT.split(value)]
    return found


def check_cors(probe: Probe) -> CheckOutcome:
    headers = _headers(probe.get(probe.url, {"Origin": PROBE_ORIGIN}))
    allow = headers.get("access-control-allow-origin", "")
    credentials = headers.get("access-control-allow-credentials", "").lower() == "true"
    findings = []
    if allow == PROBE_ORIGIN and credentials:
        findings.append(
            SecurityFinding(
                "cors", "Arbitrary origin is reflected with credentials", "high", True,
                f"A request from {PROBE_ORIGIN} got Access-Control-Allow-Origin "
                "reflecting it and Allow-Credentials: true.",
                "A05 Security Misconfiguration",
            )
        )  # fmt: skip
    elif allow == "*" and credentials:
        findings.append(
            SecurityFinding(
                "cors", "Wildcard origin with credentials", "medium", True,
                "Access-Control-Allow-Origin is * and Allow-Credentials is true.",
                "A05 Security Misconfiguration",
            )
        )  # fmt: skip
    elif allow in ("*", PROBE_ORIGIN):
        findings.append(
            SecurityFinding(
                "cors", "Cross-origin access is open", "low", False,
                f"Access-Control-Allow-Origin is {allow}. This is expected for a "
                "public API; confirm that nothing private is served here.",
                "A05 Security Misconfiguration",
            )
        )  # fmt: skip
    return CheckOutcome("cors", 1, tuple(findings))


def check_https_redirect(probe: Probe) -> CheckOutcome:
    parts = urlsplit(probe.url)
    if parts.scheme != "http":
        return CheckOutcome("https-redirect", 0, (), "The target is already HTTPS.")
    response = probe.get(probe.url)
    location = _headers(response).get("location", "")
    if 300 <= response.status < 400 and location.startswith("https://"):
        return CheckOutcome("https-redirect", 1)
    return CheckOutcome(
        "https-redirect",
        1,
        (
            SecurityFinding(
                "https-redirect", "HTTP is not redirected to HTTPS", "medium", True,
                f"The plain HTTP URL answered {response.status} without redirecting "
                "to https.",
                "A02 Cryptographic Failures",
            ),
        ),
    )  # fmt: skip


def check_unauthenticated_access(probe: Probe) -> CheckOutcome:
    if not probe.protected_paths:
        return CheckOutcome(
            "unauthenticated-access", 0, (),
            "No protected path was given (--protected-path), so nothing was tested.",
        )  # fmt: skip
    base = f"{urlsplit(probe.url).scheme}://{urlsplit(probe.url).netloc}"
    findings = []
    for path in probe.protected_paths:
        response = probe.get(base + "/" + path.lstrip("/"))
        if response.status == 200:
            findings.append(
                SecurityFinding(
                    "unauthenticated-access", f"{path} answers without credentials",
                    "high", True,
                    f"GET {path} without credentials returned 200. You declared this "
                    "path requires authentication.",
                    "A01 Broken Access Control",
                )
            )  # fmt: skip
    return CheckOutcome(
        "unauthenticated-access", len(probe.protected_paths), tuple(findings)
    )


CHECKS: dict[str, Callable[[Probe], CheckOutcome]] = {
    "headers": check_headers,
    "info-disclosure": check_info_disclosure,
    "cookies": check_cookies,
    "cors": check_cors,
    "https-redirect": check_https_redirect,
    "unauthenticated-access": check_unauthenticated_access,
}
