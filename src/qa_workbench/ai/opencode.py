"""The OpenCode adapter, isolated from the rest of the workbench (spec 7.3).

It talks to a running ``opencode serve`` through its documented HTTP API (no
internal or undocumented interfaces, no Node bridge): ``GET /global/health``,
``POST /session``, ``POST /session/:id/message``, ``POST /session/:id/abort``,
and ``GET /config/providers``. Authentication is the server's HTTP basic auth
(``OPENCODE_SERVER_USERNAME`` / ``OPENCODE_SERVER_PASSWORD``), read from the
environment and never stored.

Compatibility: written against the server API documented at
https://opencode.ai/docs/server/ in October 2026. Behaviour of other versions is
not assumed: the version reported by the server is shown, and a reply that does
not have the documented shape is an explicit error. OpenCode runs its own tools,
so this adapter does not offer workbench tool calls, structured output, or
streaming, and says so (:class:`CapabilityNotSupported`) instead of faking them.
"""

import base64
import threading
from collections.abc import Iterator, Mapping
from typing import Any

from qa_workbench.ai.contract import (
    Availability,
    CancelToken,
    Capabilities,
    CompletionRequest,
    CompletionResult,
    StreamEvent,
)
from qa_workbench.ai.errors import (
    CapabilityNotSupported,
    ProviderCancelled,
    ProviderRateLimited,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from qa_workbench.ai.http import JsonHttp, JsonResponse, TransportFailure
from qa_workbench.security.credentials import CredentialError, default_environment

DEFAULT_URL = "http://127.0.0.1:4096"
NAME = "opencode"
_POLL_SECONDS = 0.1


class OpenCodeProvider:
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

    # -- availability --------------------------------------------------------

    def check_availability(self) -> Availability:
        try:
            response = self._http.request(
                "GET", f"{self._base}/global/health", headers=self._auth(), timeout=5
            )
        except ProviderUnavailable as error:
            return Availability(False, str(error))
        except TransportFailure as error:
            return Availability(
                False,
                f"OpenCode is not reachable at {self._base} ({error.kind}). "
                "Start it with `opencode serve`.",
            )
        if response.status in (401, 403):
            return Availability(
                False,
                "OpenCode rejected the credentials. Keep the password with "
                "`batman config token set opencode` or set OPENCODE_SERVER_PASSWORD "
                "(and OPENCODE_SERVER_USERNAME if you changed it).",
            )
        body = response.body
        if (
            response.status != 200
            or not isinstance(body, dict)
            or body.get("healthy") is not True
        ):
            return Availability(
                False,
                f"{self._base} did not report a healthy OpenCode server "
                f"(HTTP {response.status}).",
            )
        version = str(body.get("version", ""))
        return Availability(True, f"OpenCode {version} at {self._base}", version)

    def list_models(self) -> list[str]:
        body = self._call("GET", "/config/providers", None, timeout=10)
        try:
            return sorted(
                f"{provider['id']}/{model_id}"
                for provider in body["providers"]
                for model_id in provider["models"]
            )
        except (KeyError, TypeError) as error:
            raise ProviderResponseError(
                NAME, f"/config/providers has an unexpected shape ({error})"
            ) from error

    # -- completion ----------------------------------------------------------

    def complete(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> CompletionResult:
        if request.tools:
            raise CapabilityNotSupported(
                NAME,
                "workbench tool calls are not supported (OpenCode runs its own tools)",
            )
        if request.response_schema is not None:
            raise CapabilityNotSupported(
                NAME, "structured output is not supported; ask for JSON in the prompt"
            )
        session = self._call(
            "POST", "/session", {"title": "Dark Knight QA"}, timeout=15
        )
        session_id = session.get("id") if isinstance(session, dict) else None
        if not isinstance(session_id, str):
            raise ProviderResponseError(NAME, "POST /session returned no session id")

        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        prompt = "\n\n".join(
            f"{m.role}: {m.content}" for m in request.messages if m.role != "system"
        )
        payload: dict[str, Any] = {"parts": [{"type": "text", "text": prompt}]}
        if system:
            payload["system"] = system
        model = request.model or self._model
        if model:
            provider_id, _, model_id = model.partition("/")
            if not model_id:
                raise ProviderResponseError(
                    NAME, f"model {model!r} must look like provider/model"
                )
            payload["model"] = {"providerID": provider_id, "modelID": model_id}

        body = self._send_cancellable(session_id, payload, request, cancel)
        return self._result(body, model)

    def stream(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> Iterator[StreamEvent]:
        raise CapabilityNotSupported(NAME, "streaming is not supported; use complete()")

    # -- internals -----------------------------------------------------------

    def _auth(self) -> dict[str, str]:
        try:
            password = self._environment.get("OPENCODE_SERVER_PASSWORD", "")
        except CredentialError as error:
            raise ProviderUnavailable(NAME, str(error)) from error
        if not password:
            return {}
        user = self._environment.get("OPENCODE_SERVER_USERNAME", "opencode")
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def _send_cancellable(
        self,
        session_id: str,
        payload: dict[str, Any],
        request: CompletionRequest,
        cancel: CancelToken | None,
    ) -> Any:
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["body"] = self._call(
                    "POST",
                    f"/session/{session_id}/message",
                    payload,
                    timeout=request.timeout_seconds,
                )
            except Exception as error:  # re-raised in the caller's thread
                outcome["error"] = error

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        while worker.is_alive():
            worker.join(_POLL_SECONDS)
            if cancel is not None and cancel.cancelled:
                self._abort(session_id)
                raise ProviderCancelled(NAME, "the request was cancelled")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["body"]

    def _abort(self, session_id: str) -> None:
        try:
            self._http.request(
                "POST",
                f"{self._base}/session/{session_id}/abort",
                headers=self._auth(),
                timeout=5,
            )
        except TransportFailure:
            pass  # the caller is told it was cancelled; the server may be gone

    def _call(self, method: str, path: str, body: Any, *, timeout: float) -> Any:
        try:
            response = self._http.request(
                method,
                f"{self._base}{path}",
                body=body,
                headers=self._auth(),
                timeout=timeout,
            )
        except TransportFailure as error:
            if error.kind == "timeout":
                raise ProviderTimeout(
                    NAME, "no answer in time", hint="Raise the timeout"
                ) from error
            raise ProviderUnavailable(
                NAME,
                f"cannot reach the server ({error})",
                hint="Is `opencode serve` running?",
            ) from error
        self._raise_for_status(path, response)
        return response.body

    @staticmethod
    def _raise_for_status(path: str, response: JsonResponse) -> None:
        status = response.status
        if status < 400:
            return
        if status in (401, 403):
            raise ProviderUnavailable(
                NAME,
                f"{path} rejected the credentials (HTTP {status})",
                hint="Set OPENCODE_SERVER_PASSWORD",
            )
        if status == 429:
            raise ProviderRateLimited(NAME, "rate limited", hint="Retry later")
        raise ProviderResponseError(NAME, f"{path} failed with HTTP {status}")

    @staticmethod
    def _result(body: Any, model: str) -> CompletionResult:
        if not isinstance(body, dict) or not isinstance(body.get("parts"), list):
            raise ProviderResponseError(
                NAME,
                "the reply does not have the documented {info, parts} shape",
                hint="The OpenCode version may be incompatible",
            )
        text = "".join(
            str(part.get("text", ""))
            for part in body["parts"]
            if isinstance(part, dict) and part.get("type") == "text"
        )
        if not text.strip():
            raise ProviderResponseError(NAME, "the reply has no text part")
        return CompletionResult(text, model)
