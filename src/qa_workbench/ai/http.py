"""A small JSON-over-HTTP port for providers, with an HTTPX adapter."""

import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Protocol


class TransportFailure(Exception):
    """No HTTP response: ``kind`` is ``timeout`` or ``connection``."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class JsonResponse:
    status: int
    body: Any
    headers: dict[str, str]


class JsonHttp(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> JsonResponse: ...

    def stream_lines(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> Iterator[str]:
        """Yield response lines; raises ``TransportFailure`` or ``StatusFailure``."""
        ...


class StatusFailure(Exception):
    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.text = text


class HttpxJson:
    def __init__(self, client: Any = None) -> None:
        import httpx

        logging.getLogger("httpx").setLevel(logging.WARNING)
        self._httpx = httpx
        self._client = client or httpx.Client(follow_redirects=False)

    def request(self, method, url, *, body=None, headers=None, timeout=30.0):
        httpx = self._httpx
        try:
            response = self._client.request(
                method, url, json=body, headers=headers, timeout=timeout
            )
        except httpx.TimeoutException as error:
            raise TransportFailure("timeout", str(error)) from error
        except httpx.HTTPError as error:
            raise TransportFailure("connection", str(error)) from error
        try:
            data = response.json() if response.content else None
        except ValueError:
            data = response.text
        return JsonResponse(response.status_code, data, dict(response.headers))

    def stream_lines(self, method, url, *, body=None, headers=None, timeout=30.0):
        httpx = self._httpx
        try:
            with self._client.stream(
                method, url, json=body, headers=headers, timeout=timeout
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    raise StatusFailure(response.status_code, response.text[:300])
                for line in response.iter_lines():
                    if line.strip():
                        yield line
        except httpx.TimeoutException as error:
            raise TransportFailure("timeout", str(error)) from error
        except httpx.HTTPError as error:
            raise TransportFailure("connection", str(error)) from error


def parse_json_line(line: str) -> dict[str, Any]:
    data = json.loads(line)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data
