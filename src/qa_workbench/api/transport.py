"""The HTTP port and its HTTPX adapter."""

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from qa_workbench.api.errors import ApiTransportError


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    json: Any = None
    body: str | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float
    url: str


class HttpTransport(Protocol):
    def send(self, request: PreparedRequest) -> TransportResponse:
        """Send a request. Raises :class:`ApiTransportError` when it cannot."""
        ...


class HttpxTransport:
    """Sends requests with HTTPX. Redirects are not followed, so a test sees
    the redirect itself instead of silently landing somewhere else."""

    def __init__(self, client: Any = None) -> None:
        import httpx

        self._httpx = httpx
        self._client = client or httpx.Client(follow_redirects=False)

    def send(self, request: PreparedRequest) -> TransportResponse:
        httpx = self._httpx
        started = time.perf_counter()
        try:
            response = self._client.request(
                request.method,
                request.url,
                headers=request.headers,
                params=request.params or None,
                json=request.json,
                content=request.body.encode("utf-8") if request.body else None,
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise ApiTransportError(
                f"timed out after {request.timeout_seconds:g}s",
                method=request.method,
                url=request.url,
            ) from error
        except httpx.HTTPError as error:
            raise ApiTransportError(
                f"{type(error).__name__}: {error}",
                method=request.method,
                url=request.url,
            ) from error
        elapsed = (time.perf_counter() - started) * 1000
        return TransportResponse(
            response.status_code,
            dict(response.headers),
            response.content,
            elapsed,
            str(response.url),
        )
