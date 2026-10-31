"""The hosted NVIDIA adapter: the NVIDIA API Catalog's OpenAI-compatible API.

Uses two documented endpoints, ``GET /models`` and ``POST /chat/completions``,
under a base URL that stays configurable (``DEFAULT_URL`` is the hosted catalog,
https://build.nvidia.com, as documented in October 2026). Unlike the local
engines this one sends data off the machine, so:

* it is never chosen implicitly (``auto`` skips it) and the UI says it is remote;
* every request is checked by the action guard first (see :mod:`.guarded`);
* message text goes through ``redact_secrets`` before it is sent;
* the API key comes from ``NVIDIA_API_KEY`` or ``batman config token set nvidia``
  and appears in no output, error message, log, or audit entry.

It does not offer workbench tool calls or structured output, and says so
(:class:`CapabilityNotSupported`) instead of faking them.
"""

from collections.abc import Iterator, Mapping
from typing import Any
from urllib.parse import urlsplit

from qa_workbench.ai.contract import (
    Availability,
    CancelToken,
    Capabilities,
    CompletionRequest,
    CompletionResult,
    Message,
    StreamEvent,
    Usage,
)
from qa_workbench.ai.errors import (
    CapabilityNotSupported,
    ProviderCancelled,
    ProviderRateLimited,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from qa_workbench.ai.http import JsonHttp, TransportFailure
from qa_workbench.core.secrets import redact_secrets
from qa_workbench.security.credentials import CredentialError, default_environment

DEFAULT_URL = "https://integrate.api.nvidia.com/v1"
NAME = "nvidia"
KEY_VARIABLE = "NVIDIA_API_KEY"
_KEY_HINT = "Keep it with `batman config token set nvidia` or set NVIDIA_API_KEY"
_MAX_DETAIL = 200


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or url).lower()


def _message(message: Message) -> dict[str, str]:
    return {"role": message.role, "content": redact_secrets(message.content)}


class NvidiaProvider:
    name = NAME
    capabilities = Capabilities(lists_models=True)

    def __init__(
        self,
        http: JsonHttp,
        *,
        base_url: str = DEFAULT_URL,
        model: str = "",
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._http = http
        self._base = base_url.rstrip("/")
        self._model = model
        # The environment first, then the value kept with `batman config token`.
        self._environment = (
            default_environment() if environment is None else environment
        )

    def key_present(self) -> bool:
        try:
            return bool(self._environment.get(KEY_VARIABLE, ""))
        except CredentialError:
            return False

    # -- availability --------------------------------------------------------

    def check_availability(self) -> Availability:
        try:
            self._headers()
            models = self.list_models()
        except ProviderUnavailable as error:
            return Availability(False, str(error))
        except (ProviderTimeout, ProviderRateLimited, ProviderResponseError) as error:
            return Availability(False, str(error))
        return Availability(
            True, f"NVIDIA API at {self._base} ({len(models)} models; remote)"
        )

    def list_models(self) -> list[str]:
        body = self._call("GET", "/models", None, timeout=15)
        try:
            return sorted(str(item["id"]) for item in body["data"])
        except (KeyError, TypeError) as error:
            raise ProviderResponseError(
                NAME, f"{self._base}/models has an unexpected shape ({error})"
            ) from error

    # -- completion ----------------------------------------------------------

    def complete(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> CompletionResult:
        if request.tools:
            raise CapabilityNotSupported(
                NAME, "workbench tool calls are not supported by this engine"
            )
        if request.response_schema is not None:
            raise CapabilityNotSupported(
                NAME, "structured output is not supported; ask for JSON in the prompt"
            )
        model = request.model or self._model
        if not model:
            raise ProviderResponseError(
                NAME,
                "no model is configured",
                hint="Pass one with --model; list them with "
                "`batman ai models --engine nvidia`",
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_message(m) for m in request.messages],
            "stream": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        self._check_cancel(cancel)
        body = self._call(
            "POST", "/chat/completions", payload, timeout=request.timeout_seconds
        )
        self._check_cancel(cancel)
        return self._result(body, model)

    def stream(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> Iterator[StreamEvent]:
        raise CapabilityNotSupported(NAME, "streaming is not supported; use complete()")

    # -- internals -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        try:
            key = self._environment.get(KEY_VARIABLE, "")
        except CredentialError as error:
            raise ProviderUnavailable(NAME, str(error)) from error
        if not key:
            raise ProviderUnavailable(NAME, "no API key is set", hint=_KEY_HINT)
        return {"Authorization": f"Bearer {key}", "Accept": "application/json"}

    def _call(self, method: str, path: str, body: Any, *, timeout: float) -> Any:
        url = f"{self._base}{path}"
        headers = self._headers()
        try:
            response = self._http.request(
                method, url, body=body, headers=headers, timeout=timeout
            )
        except TransportFailure as error:
            if error.kind == "timeout":
                raise ProviderTimeout(
                    NAME, f"{url} gave no answer in time", hint="Raise the timeout"
                ) from error
            raise ProviderUnavailable(
                NAME,
                f"cannot reach {url}",
                hint="Check the network and the NVIDIA URL",
            ) from error
        self._raise_for_status(url, response.status, response.body, headers)
        return response.body

    @staticmethod
    def _detail(body: Any, headers: dict[str, str]) -> str:
        """What the server said about a failure, with the key scrubbed."""
        text = ""
        if isinstance(body, dict):
            error = body.get("error")
            text = str(
                body.get("detail")
                or (error.get("message") if isinstance(error, dict) else error)
                or ""
            )
        elif isinstance(body, str):
            text = body
        key = headers.get("Authorization", "").removeprefix("Bearer ")
        if key:
            text = text.replace(key, "[REDACTED]")
        return redact_secrets(text).strip()[:_MAX_DETAIL]

    def _raise_for_status(
        self, url: str, status: int, body: Any, headers: dict[str, str]
    ) -> None:
        if status < 400:
            return
        if status in (401, 403):
            raise ProviderUnavailable(
                NAME, f"{url} rejected the API key (HTTP {status})", hint=_KEY_HINT
            )
        if status == 429:
            raise ProviderRateLimited(
                NAME, f"{url} is rate limited (HTTP 429)", hint="Retry later"
            )
        detail = self._detail(body, headers)
        suffix = f": {detail}" if detail else ""
        if status == 404 and url.endswith("/chat/completions"):
            raise ProviderResponseError(
                NAME,
                f"{url} does not know that model (HTTP 404){suffix}",
                hint="List the models with `batman ai models --engine nvidia`",
            )
        raise ProviderResponseError(NAME, f"{url} failed with HTTP {status}{suffix}")

    def _result(self, body: Any, model: str) -> CompletionResult:
        try:
            choice = body["choices"][0]
            text = str(choice["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderResponseError(
                NAME,
                f"{self._base}/chat/completions has an unexpected shape ({error})",
                hint="The API may have changed",
            ) from error
        if not text.strip():
            raise ProviderResponseError(NAME, "the reply has no text")
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return CompletionResult(
            text,
            str(body.get("model") or model),
            finish_reason=str(choice.get("finish_reason") or ""),
            usage=Usage(usage.get("prompt_tokens"), usage.get("completion_tokens")),
        )

    @staticmethod
    def _check_cancel(cancel: CancelToken | None) -> None:
        if cancel is not None and cancel.cancelled:
            raise ProviderCancelled(NAME, "the request was cancelled")
