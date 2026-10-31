"""Integration failures keep their diagnostic context (NFR-010).

None of these is ever turned into an empty result: an unreachable server, a bad
token, and "no issues found" are different situations and are reported as such.
Messages carry the system, the endpoint path (never the token), the HTTP status,
and a hint about what to do.
"""


class IntegrationError(Exception):
    """A call to an external system failed."""

    def __init__(
        self,
        system: str,
        message: str,
        *,
        endpoint: str = "",
        status: int | None = None,
        hint: str = "",
    ) -> None:
        details = []
        if endpoint:
            details.append(f"endpoint {endpoint}")
        if status is not None:
            details.append(f"HTTP {status}")
        text = f"{system}: {message}"
        if details:
            text += f" ({', '.join(details)})"
        if hint:
            text += f". {hint}"
        super().__init__(text)
        self.system = system
        self.endpoint = endpoint
        self.status = status
        self.hint = hint


class NotConfiguredError(IntegrationError):
    """The integration has no URL, project, or token to work with."""


class NotAuthorizedError(IntegrationError):
    """The action guard did not allow the request, so nothing was sent."""


class AuthenticationError(IntegrationError):
    """The token is missing, invalid, expired, or lacks permission."""


class NotFoundError(IntegrationError):
    """The requested resource does not exist (or is not visible to the token)."""


class RateLimitedError(IntegrationError):
    """The server asked the client to slow down."""

    def __init__(self, *args: object, retry_after: int | None = None, **kwargs: object):
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.retry_after = retry_after


class ServerError(IntegrationError):
    """The server failed (HTTP 5xx)."""


class UnreachableError(IntegrationError):
    """The server could not be reached (network, DNS, TLS, timeout)."""


class UnexpectedResponseError(IntegrationError):
    """The server answered, but not with what the API promises."""
