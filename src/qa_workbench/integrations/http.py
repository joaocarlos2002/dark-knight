"""A read-only HTTP port for integrations, with an HTTPX adapter."""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol


class GatewayError(Exception):
    """The request never produced an HTTP response."""


@dataclass(frozen=True)
class GatewayResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class GatewayRequest:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 30.0


class HttpGateway(Protocol):
    def get(self, request: GatewayRequest) -> GatewayResponse:
        """Send a GET. Raises :class:`GatewayError` when there is no response."""
        ...


class HttpxGateway:
    """Sends GET requests with HTTPX. Redirects are not followed, so a token is
    never replayed against another host."""

    def __init__(self, client: Any = None) -> None:
        import httpx

        # httpx logs request URLs at INFO; keep them out of the log.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self._httpx = httpx
        self._client = client or httpx.Client(follow_redirects=False)

    def get(self, request: GatewayRequest) -> GatewayResponse:
        try:
            response = self._client.get(
                request.url,
                headers=request.headers,
                params=request.params or None,
                timeout=request.timeout_seconds,
            )
        except self._httpx.TimeoutException as error:
            raise GatewayError(
                f"timed out after {request.timeout_seconds:g}s"
            ) from error
        except self._httpx.HTTPError as error:
            raise GatewayError(f"{type(error).__name__}: {error}") from error
        return GatewayResponse(
            response.status_code, dict(response.headers), response.content
        )
