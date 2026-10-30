import httpx
import pytest

from qa_workbench.api.errors import ApiTransportError
from qa_workbench.api.transport import HttpxTransport, PreparedRequest


def _transport(handler) -> HttpxTransport:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return HttpxTransport(client)


def test_request_parts_reach_the_wire_and_the_answer_is_returned() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(
            method=request.method,
            url=str(request.url),
            auth=request.headers.get("authorization"),
            body=request.content,
        )
        return httpx.Response(201, json={"ok": True}, headers={"X-Id": "9"})

    response = _transport(handler).send(
        PreparedRequest(
            "POST",
            "https://api.test/items",
            {"Authorization": "Bearer t"},
            {"dry": "1"},
            json={"a": 1},
        )
    )

    assert seen["method"] == "POST" and "dry=1" in str(seen["url"])
    assert seen["auth"] == "Bearer t" and b'"a"' in seen["body"]  # type: ignore[operator]
    assert response.status == 201 and response.headers["x-id"] == "9"
    assert response.elapsed_ms >= 0


def test_redirects_are_reported_not_followed() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(302, headers={"Location": "/elsewhere"})
        ),
        follow_redirects=False,
    )

    response = HttpxTransport(client).send(PreparedRequest("GET", "https://a.test/"))

    assert response.status == 302


def test_timeout_and_connection_errors_are_explicit() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ApiTransportError, match="timed out after 2s"):
        _transport(timeout).send(
            PreparedRequest("GET", "https://a.test/", timeout_seconds=2)
        )
    with pytest.raises(ApiTransportError, match="ConnectError") as error:
        _transport(refused).send(PreparedRequest("GET", "https://a.test/x"))
    assert error.value.url == "https://a.test/x"
