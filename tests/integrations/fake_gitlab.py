"""A scripted GitLab for tests: routes map an API path to a JSON answer."""

import json
from typing import Any

from qa_workbench.integrations.gitlab.client import GitLabClient, GitLabConnection
from qa_workbench.integrations.http import (
    GatewayError,
    GatewayRequest,
    GatewayResponse,
)

BASE = "https://gitlab.test"
PROJECT = "group/app"
TOKEN = "glpat-test-token-0123456789"
PREFIX = "/api/v4/projects/group%2Fapp"


def answer(
    body: Any, status: int = 200, headers: dict[str, str] | None = None
) -> GatewayResponse:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return GatewayResponse(status, headers or {}, raw)


class FakeGateway:
    """Serves routes by path (without query). Unknown routes are 404."""

    def __init__(self, routes: dict[str, Any] | None = None) -> None:
        self.routes = routes or {}
        self.requests: list[GatewayRequest] = []
        self.failure: GatewayError | None = None

    def get(self, request: GatewayRequest) -> GatewayResponse:
        self.requests.append(request)
        if self.failure:
            raise self.failure
        path = request.url.removeprefix(BASE)
        if path not in self.routes:
            return answer({"message": "404 Not found"}, 404)
        route = self.routes[path]
        return route(request) if callable(route) else answer(route)


def make_client(
    gateway: FakeGateway, environment: dict[str, str] | None = None
) -> GitLabClient:
    return GitLabClient(
        GitLabConnection(BASE, PROJECT),
        gateway,
        environment={"GITLAB_TOKEN": TOKEN} if environment is None else environment,
    )
