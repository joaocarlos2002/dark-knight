"""Fakes for AI tests: no network and no model."""

import json
from collections.abc import Iterator
from typing import Any

from qa_workbench.ai.claude_code import ProcessResult
from qa_workbench.ai.contract import (
    Availability,
    Capabilities,
    CompletionRequest,
    CompletionResult,
    StreamEvent,
    ToolCall,
)
from qa_workbench.ai.errors import ProviderUnavailable
from qa_workbench.ai.http import JsonResponse, StatusFailure, TransportFailure


class FakeHttp:
    """Answers by (method, path suffix). A value may be a response, a list of
    stream lines, an exception, or a callable taking the request body."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, Any, dict[str, str]]] = []

    def _route(self, method: str, url: str, body: Any, headers: Any) -> Any:
        self.calls.append((method, url, body, dict(headers or {})))
        for (m, suffix), value in self.routes.items():
            if m == method and url.endswith(suffix):
                if callable(value):
                    value = value(body)
                if isinstance(value, Exception):
                    raise value
                return value
        return JsonResponse(404, {"error": "no route"}, {})

    def request(self, method, url, *, body=None, headers=None, timeout=30.0):
        return self._route(method, url, body, headers)

    def stream_lines(self, method, url, *, body=None, headers=None, timeout=30.0):
        value = self._route(method, url, body, headers)
        if isinstance(value, JsonResponse):
            raise StatusFailure(value.status, str(value.body))
        yield from value


def ok(body: Any, status: int = 200) -> JsonResponse:
    return JsonResponse(status, body, {})


def lines(*chunks: dict[str, Any]) -> list[str]:
    return [json.dumps(chunk) for chunk in chunks]


def down() -> TransportFailure:
    return TransportFailure("connection", "refused")


class FakeProvider:
    """Replies from a script: each item is a CompletionResult or an exception."""

    def __init__(
        self,
        script: list[CompletionResult | Exception],
        *,
        name: str = "fake",
        tools: bool = True,
        structured: bool = True,
        available: bool = True,
    ) -> None:
        self.name = name
        self.capabilities = Capabilities(tools=tools, structured_output=structured)
        self.script = list(script)
        self.requests: list[CompletionRequest] = []
        self._available = available

    def check_availability(self) -> Availability:
        return Availability(self._available, "up" if self._available else "down")

    def list_models(self) -> list[str]:
        return ["m"]

    def complete(self, request: CompletionRequest, cancel=None) -> CompletionResult:
        self.requests.append(request)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def stream(self, request, cancel=None) -> Iterator[StreamEvent]:
        yield from ()


def reply(text: str, *calls: ToolCall) -> CompletionResult:
    return CompletionResult(text, "m", tuple(calls))


def answer(*statements: dict[str, Any]) -> str:
    return json.dumps({"statements": list(statements)})


class FakeRunner:
    """Stands in for the Claude Code process: nothing is started."""

    def __init__(
        self,
        stdout: str = "",
        *,
        returncode: int = 0,
        stderr: str = "",
        version: str | None = "2.1.0 (Claude Code)",
    ) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr
        self.version = version
        self.runs: list[tuple[list[str], str]] = []

    def run(self, args, stdin, timeout, cancel=None):
        self.runs.append((list(args), stdin))
        return ProcessResult(self.returncode, self.stdout, self.stderr)

    def probe(self, args):
        if self.version is None:
            raise ProviderUnavailable("claude", "cannot start Claude Code")
        return ProcessResult(0, self.version + "\n", "")


def claude_reply(text: str, **extra: Any) -> str:
    """What `claude -p --output-format json` prints."""
    return json.dumps(
        {
            "result": text,
            "is_error": False,
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 3},
            **extra,
        }
    )
