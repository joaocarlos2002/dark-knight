"""The Ollama adapter: a local model runtime (spec 7.2).

Uses Ollama's documented REST API: ``/api/version``, ``/api/tags``, and
``/api/chat`` (NDJSON when streaming). The server is local; nothing leaves the
machine unless the configured URL points elsewhere.
"""

from collections.abc import Iterator
from typing import Any

from qa_workbench.ai.contract import (
    Availability,
    CancelToken,
    Capabilities,
    CompletionRequest,
    CompletionResult,
    Message,
    StreamEvent,
    ToolCall,
    Usage,
)
from qa_workbench.ai.errors import (
    ProviderCancelled,
    ProviderRateLimited,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from qa_workbench.ai.http import (
    JsonHttp,
    StatusFailure,
    TransportFailure,
    parse_json_line,
)

DEFAULT_URL = "http://127.0.0.1:11434"
NAME = "ollama"


def _message(message: Message) -> dict[str, Any]:
    data: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        data["tool_calls"] = [
            {"function": {"name": c.name, "arguments": c.arguments}}
            for c in message.tool_calls
        ]
    if message.tool_name:
        data["tool_name"] = message.tool_name
    return data


class OllamaProvider:
    name = NAME
    capabilities = Capabilities(
        streaming=True, tools=True, structured_output=True, lists_models=True
    )

    def __init__(
        self, http: JsonHttp, *, base_url: str = DEFAULT_URL, model: str = ""
    ) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._model = model

    # -- availability --------------------------------------------------------

    def check_availability(self) -> Availability:
        try:
            response = self._http.request("GET", f"{self._base}/api/version", timeout=5)
        except TransportFailure as error:
            return Availability(
                False,
                f"Ollama is not reachable at {self._base} ({error.kind}). "
                "Start it with `ollama serve`.",
            )
        version = (
            response.body.get("version", "")
            if response.status == 200 and isinstance(response.body, dict)
            else ""
        )
        if not version:
            return Availability(
                False,
                f"{self._base} answered HTTP {response.status} without an Ollama "
                "version; is it an Ollama server?",
            )
        return Availability(True, f"Ollama {version} at {self._base}", str(version))

    def list_models(self) -> list[str]:
        body = self._json("GET", "/api/tags", None, timeout=10)
        try:
            return [str(model["name"]) for model in body["models"]]
        except (KeyError, TypeError) as error:
            raise ProviderResponseError(NAME, f"/api/tags has no {error}") from error

    # -- completion ----------------------------------------------------------

    def complete(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> CompletionResult:
        payload = self._payload(request, stream=False)
        self._check_cancel(cancel)
        body = self._json("POST", "/api/chat", payload, timeout=request.timeout_seconds)
        self._check_cancel(cancel)
        return self._result(body, request)

    def stream(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> Iterator[StreamEvent]:
        payload = self._payload(request, stream=True)
        text: list[str] = []
        calls: list[ToolCall] = []
        final: dict[str, Any] = {}
        try:
            for line in self._http.stream_lines(
                "POST",
                f"{self._base}/api/chat",
                body=payload,
                timeout=request.timeout_seconds,
            ):
                self._check_cancel(cancel)
                try:
                    chunk = parse_json_line(line)
                except ValueError as error:
                    raise ProviderResponseError(
                        NAME, f"a stream line is not JSON ({error})"
                    ) from error
                if "error" in chunk:
                    raise ProviderResponseError(NAME, str(chunk["error"]))
                message = chunk.get("message") or {}
                if message.get("content"):
                    text.append(message["content"])
                    yield StreamEvent("text", message["content"])
                for call in self._calls(message):
                    calls.append(call)
                    yield StreamEvent("tool_call", tool_call=call)
                if chunk.get("done"):
                    final = chunk
                    break
        except TransportFailure as error:
            raise self._transport_error(error) from error
        except StatusFailure as error:
            raise self._status_error(error.status, error.text) from error
        if not final:
            raise ProviderResponseError(
                NAME, "the stream ended before the final message", hint="Retry"
            )
        yield StreamEvent(
            "done",
            result=CompletionResult(
                "".join(text),
                str(final.get("model", request.model or self._model)),
                tuple(calls),
                str(final.get("done_reason", "")),
                self._usage(final),
            ),
        )

    # -- internals -----------------------------------------------------------

    def _payload(self, request: CompletionRequest, *, stream: bool) -> dict[str, Any]:
        model = request.model or self._model
        if not model:
            raise ProviderResponseError(
                NAME,
                "no model is configured",
                hint="Pass a model, for example `--model llama3.2`",
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_message(m) for m in request.messages],
            "stream": stream,
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in request.tools
            ]
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        if request.temperature is not None:
            payload["options"] = {"temperature": request.temperature}
        return payload

    def _json(self, method: str, path: str, body: Any, *, timeout: float) -> Any:
        try:
            response = self._http.request(
                method, f"{self._base}{path}", body=body, timeout=timeout
            )
        except TransportFailure as error:
            raise self._transport_error(error) from error
        if response.status >= 400:
            detail = (
                response.body.get("error") if isinstance(response.body, dict) else ""
            )
            raise self._status_error(response.status, str(detail or ""))
        if not isinstance(response.body, dict):
            raise ProviderResponseError(NAME, f"{path} did not return a JSON object")
        if "error" in response.body:
            raise ProviderResponseError(NAME, str(response.body["error"]))
        return response.body

    def _result(
        self, body: dict[str, Any], request: CompletionRequest
    ) -> CompletionResult:
        message = body.get("message")
        if not isinstance(message, dict):
            raise ProviderResponseError(NAME, "the reply has no message")
        return CompletionResult(
            str(message.get("content") or ""),
            str(body.get("model", request.model or self._model)),
            tuple(self._calls(message)),
            str(body.get("done_reason", "")),
            self._usage(body),
        )

    @staticmethod
    def _calls(message: dict[str, Any]) -> list[ToolCall]:
        calls = []
        for item in message.get("tool_calls") or []:
            function = item.get("function") or {}
            if not function.get("name"):
                raise ProviderResponseError(NAME, "a tool call has no name")
            arguments = function.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ProviderResponseError(
                    NAME, "tool call arguments are not an object"
                )
            calls.append(ToolCall(str(function["name"]), arguments))
        return calls

    @staticmethod
    def _usage(body: dict[str, Any]) -> Usage:
        return Usage(body.get("prompt_eval_count"), body.get("eval_count"))

    @staticmethod
    def _check_cancel(cancel: CancelToken | None) -> None:
        if cancel is not None and cancel.cancelled:
            raise ProviderCancelled(NAME, "the request was cancelled")

    @staticmethod
    def _transport_error(error: TransportFailure) -> Exception:
        if error.kind == "timeout":
            return ProviderTimeout(NAME, "no answer in time", hint="Raise the timeout")
        return ProviderUnavailable(
            NAME,
            f"cannot reach the server ({error})",
            hint="Is `ollama serve` running?",
        )

    @staticmethod
    def _status_error(status: int, detail: str) -> Exception:
        if status == 404:
            return ProviderResponseError(
                NAME,
                f"HTTP 404 {detail}".strip(),
                hint="The model may not be installed: `ollama pull <model>`",
            )
        if status == 429:
            return ProviderRateLimited(NAME, "rate limited", hint="Retry later")
        return ProviderResponseError(NAME, f"HTTP {status} {detail}".strip())
