"""The GitLab REST client: authentication, pagination, and explicit failures."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit

from qa_workbench.integrations.errors import (
    AuthenticationError,
    IntegrationError,
    NotConfiguredError,
    NotFoundError,
    RateLimitedError,
    ServerError,
    UnexpectedResponseError,
    UnreachableError,
)
from qa_workbench.integrations.http import (
    GatewayError,
    GatewayRequest,
    GatewayResponse,
    HttpGateway,
)
from qa_workbench.security.credentials import CredentialError, default_environment

SYSTEM = "GitLab"
DEFAULT_TOKEN_ENV = "GITLAB_TOKEN"
PAGE_SIZE = 100


@dataclass(frozen=True)
class GitLabConnection:
    """Where the GitLab project is. The token is named, never stored."""

    base_url: str
    project_path: str
    token_env: str = DEFAULT_TOKEN_ENV

    @classmethod
    def from_repository_url(
        cls, url: str, *, token_env: str = DEFAULT_TOKEN_ENV
    ) -> "GitLabConnection":
        """Derive the connection from a project's repository URL.

        ``https://gitlab.example.com/group/sub/app.git`` becomes the server
        ``https://gitlab.example.com`` and the project ``group/sub/app``.
        """
        parts = urlsplit(url)
        path = parts.path.strip("/").removesuffix(".git")
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or "/" not in path
        ):
            raise NotConfiguredError(
                SYSTEM,
                f"cannot read a GitLab project from {url!r}",
                hint="Use an http(s) URL such as https://gitlab.example.com/group/app",
            )
        if parts.username or parts.password:
            raise NotConfiguredError(
                SYSTEM,
                "the repository URL must not embed credentials",
                hint="Keep the token in an environment variable",
            )
        host = parts.hostname + (f":{parts.port}" if parts.port else "")
        return cls(f"{parts.scheme}://{host}", path, token_env)


class GitLabClient:
    """Reads from one GitLab project."""

    def __init__(
        self,
        connection: GitLabConnection,
        gateway: HttpGateway,
        *,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._connection = connection
        self._gateway = gateway
        # The environment first, then tokens stored with `batman config token`.
        self._environment = (
            default_environment() if environment is None else environment
        )
        self._timeout = timeout_seconds
        self._project = quote(connection.project_path, safe="")

    # -- public helpers used by the adapters ---------------------------------

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        response = self._request(path, params)
        return self._decode(path, response)

    def get_bytes(
        self, path: str, *, max_bytes: int, params: Mapping[str, str] | None = None
    ) -> bytes:
        body = self._request(path, params).body
        if len(body) > max_bytes:
            raise UnexpectedResponseError(
                SYSTEM,
                f"the response is {len(body)} bytes, over the {max_bytes} byte limit",
                endpoint=path,
            )
        return body

    def get_list(
        self, path: str, params: Mapping[str, str] | None = None, *, limit: int
    ) -> list[Any]:
        """Collect up to ``limit`` items, following pages."""
        items: list[Any] = []
        page = 1
        while len(items) < limit:
            query = {
                **(params or {}),
                "per_page": str(min(PAGE_SIZE, limit - len(items))),
                "page": str(page),
            }
            response = self._request(path, query)
            data = self._decode(path, response)
            if not isinstance(data, list):
                raise UnexpectedResponseError(
                    SYSTEM, "expected a list", endpoint=path, status=response.status
                )
            items.extend(data)
            next_page = response.headers.get("x-next-page") or response.headers.get(
                "X-Next-Page"
            )
            if not next_page or not data:
                break
            page = int(next_page) if next_page.isdigit() else page + 1
        return items[:limit]

    @property
    def base_url(self) -> str:
        return self._connection.base_url

    @property
    def project_name(self) -> str:
        """The project's path, such as ``group/sub/app``."""
        return self._connection.project_path

    def project_path(self, suffix: str) -> str:
        return f"/projects/{self._project}{suffix}"

    # -- internals -----------------------------------------------------------

    def _token(self) -> str:
        name = self._connection.token_env
        try:
            token = self._environment.get(name, "")
        except CredentialError as error:
            raise NotConfiguredError(SYSTEM, str(error)) from error
        if not token:
            raise NotConfiguredError(
                SYSTEM,
                f"environment variable {name} is not set",
                hint=(
                    "Create a token with the read_api scope and export it as "
                    f"{name}, or keep it with `batman config token set {name}`"
                ),
            )
        return token

    def post_json(self, path: str, body: Mapping[str, Any]) -> Any:
        """POST JSON. A network failure here leaves the outcome unknown: the
        server may have acted before the connection broke."""
        response = self._send("POST", path, None, dict(body))
        return self._decode(path, response)

    def _request(self, path: str, params: Mapping[str, str] | None) -> GatewayResponse:
        return self._send("GET", path, params, None)

    def _send(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None,
        body: dict[str, Any] | None,
    ) -> GatewayResponse:
        token = self._token()
        request = GatewayRequest(
            f"{self._connection.base_url}/api/v4{path}",
            {"PRIVATE-TOKEN": token, "Accept": "application/json"},
            dict(params or {}),
            self._timeout,
            body,
        )
        try:
            response = (
                self._gateway.post(request)
                if method == "POST"
                else self._gateway.get(request)
            )
        except GatewayError as error:
            hint = f"Check that {self._connection.base_url} is reachable"
            if method == "POST":
                hint = (
                    "The request may or may not have been applied; check GitLab "
                    "before retrying"
                )
            raise UnreachableError(
                SYSTEM,
                str(error).replace(token, "[REDACTED]"),
                endpoint=path,
                hint=hint,
            ) from error
        self._raise_for_status(path, response)
        return response

    @staticmethod
    def _raise_for_status(path: str, response: GatewayResponse) -> None:
        status = response.status
        if 200 <= status < 300:
            return
        if status == 401:
            raise AuthenticationError(
                SYSTEM,
                "the token was rejected",
                endpoint=path,
                status=status,
                hint="It may be invalid or expired",
            )
        if status == 403:
            raise AuthenticationError(
                SYSTEM,
                "the token is not allowed to read this",
                endpoint=path,
                status=status,
                hint="Check its scope (read_api) and your role in the project",
            )
        if status == 404:
            raise NotFoundError(
                SYSTEM,
                "not found",
                endpoint=path,
                status=status,
                hint="The resource may not exist, or the token cannot see it",
            )
        if status == 429:
            wait = response.headers.get("retry-after") or response.headers.get(
                "Retry-After"
            )
            raise RateLimitedError(
                SYSTEM,
                "rate limited",
                endpoint=path,
                status=status,
                hint=f"Retry in {wait} seconds" if wait else "Retry later",
                retry_after=int(wait) if wait and wait.isdigit() else None,
            )
        if status >= 500:
            raise ServerError(SYSTEM, "the server failed", endpoint=path, status=status)
        raise IntegrationError(
            SYSTEM, "unexpected response", endpoint=path, status=status
        )

    @staticmethod
    def _decode(path: str, response: GatewayResponse) -> Any:
        try:
            return json.loads(response.body.decode("utf-8"))
        except ValueError as error:
            raise UnexpectedResponseError(
                SYSTEM,
                "the response is not JSON",
                endpoint=path,
                status=response.status,
                hint="Is the URL a GitLab server?",
            ) from error
