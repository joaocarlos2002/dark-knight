"""A scripted HTTP transport for tests: no network."""

import json
from collections.abc import Callable
from typing import Any

from qa_workbench.api.errors import ApiTransportError
from qa_workbench.api.transport import PreparedRequest, TransportResponse

Handler = Callable[[PreparedRequest], TransportResponse | Exception]


def reply(
    status: int = 200,
    body: Any = None,
    headers: dict[str, str] | None = None,
    elapsed_ms: float = 12.0,
) -> TransportResponse:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return TransportResponse(
        status,
        {"Content-Type": "application/json", **(headers or {})},
        raw if body is not None else b"",
        elapsed_ms,
        "https://api.test/",
    )


class FakeTransport:
    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.requests: list[PreparedRequest] = []

    def send(self, request: PreparedRequest) -> TransportResponse:
        self.requests.append(request)
        outcome = self.handler(request)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def unreachable(request: PreparedRequest) -> ApiTransportError:
    return ApiTransportError(
        "connection refused", method=request.method, url=request.url
    )
