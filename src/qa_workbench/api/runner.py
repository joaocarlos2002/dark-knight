"""Runs API tests: requests, authentication, checks, timing, and chained flows."""

import base64
import json
import os
import re
from collections.abc import Mapping
from typing import Any

import jsonschema

from qa_workbench.api.errors import ApiError, ApiTransportError
from qa_workbench.api.models import (
    ERROR,
    FAILED,
    PASSED,
    SKIPPED,
    ApiDefinition,
    ApiStep,
    AuthSpec,
    CheckResult,
    Exchange,
    Expectation,
    FlowResult,
    StepResult,
)
from qa_workbench.api.sanitize import Sanitizer
from qa_workbench.api.transport import (
    HttpTransport,
    PreparedRequest,
    TransportResponse,
)

_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][\w.-]*)\s*\}\}")
_PATH_TOKEN = re.compile(r"\.([A-Za-z_][\w-]*)|\[(\d+)\]")


def read_path(data: Any, path: str) -> Any:
    """Read ``$.a.b[0].c`` from parsed JSON; raises ``KeyError`` when absent."""
    if not path.startswith("$"):
        raise KeyError(f"path {path!r} must start with '$'")
    rest = path[1:]
    position = 0
    current = data
    while position < len(rest):
        match = _PATH_TOKEN.match(rest, position)
        if match is None:
            raise KeyError(f"path {path!r} is not valid at {rest[position:]!r}")
        position = match.end()
        key, index = match.groups()
        try:
            current = current[key] if key is not None else current[int(index)]
        except (KeyError, IndexError, TypeError) as error:
            raise KeyError(f"{path!r} was not found in the response") from error
    return current


class ApiRunner:
    """Runs definitions through an :class:`HttpTransport`.

    Credentials come from ``environment`` (the process environment by default)
    and are registered with the sanitizer the moment they are used, so they
    cannot reach the saved result even if a server echoes them back.
    """

    def __init__(
        self,
        transport: HttpTransport,
        *,
        environment: Mapping[str, str] | None = None,
        mask_personal_data: bool = True,
    ) -> None:
        self._transport = transport
        self._environment = os.environ if environment is None else environment
        self._mask_personal_data = mask_personal_data

    def run(self, definition: ApiDefinition) -> FlowResult:
        sanitizer = Sanitizer(mask_personal_data=self._mask_personal_data)
        variables: dict[str, str] = {}
        results: list[StepResult] = []
        halted = False
        for step in definition.steps:
            if halted:
                results.append(StepResult(step.name, SKIPPED))
                continue
            result = self._run_step(definition, step, variables, sanitizer)
            results.append(result)
            if result.status != PASSED and definition.stop_on_failure:
                halted = True
        return FlowResult(
            definition.name, sanitizer.url(definition.base_url), tuple(results)
        )

    # -- one step ------------------------------------------------------------

    def _run_step(
        self,
        definition: ApiDefinition,
        step: ApiStep,
        variables: dict[str, str],
        sanitizer: Sanitizer,
    ) -> StepResult:
        try:
            request = self._prepare(definition, step, variables, sanitizer)
        except ApiError as error:
            return StepResult(step.name, ERROR, error=sanitizer.text(str(error)))
        try:
            response = self._transport.send(request)
        except ApiTransportError as error:
            return StepResult(
                step.name,
                ERROR,
                error=sanitizer.text(
                    f"{error.method} {sanitizer.url(error.url)}: {error.reason}"
                ),
                exchange=self._exchange(request, None, sanitizer),
            )
        checks, parsed = self._check(step.expect, response, sanitizer)
        try:
            self._extract(step, parsed, variables, sanitizer)
        except ApiError as error:
            checks.append(
                CheckResult("extract values", False, sanitizer.text(str(error)))
            )
        # Built last: secrets extracted from this very response must already be
        # known to the sanitizer when its body is written down.
        exchange = self._exchange(request, response, sanitizer)
        status = PASSED if all(check.passed for check in checks) else FAILED
        return StepResult(step.name, status, tuple(checks), exchange)

    def _prepare(
        self,
        definition: ApiDefinition,
        step: ApiStep,
        variables: Mapping[str, str],
        sanitizer: Sanitizer,
    ) -> PreparedRequest:
        def fill(text: str) -> str:
            def substitute(match: re.Match[str]) -> str:
                name = match.group(1)
                if name not in variables:
                    raise ApiError(
                        f"Step {step.name!r} uses {{{{{name}}}}}, which no earlier "
                        "step extracted."
                    )
                return variables[name]

            return _VARIABLE.sub(substitute, text)

        def fill_any(value: Any) -> Any:
            if isinstance(value, str):
                return fill(value)
            if isinstance(value, dict):
                return {key: fill_any(item) for key, item in value.items()}
            if isinstance(value, list):
                return [fill_any(item) for item in value]
            return value

        path = fill(step.url)
        for name, value in step.path_params.items():
            path = path.replace("{" + name + "}", fill(str(value)))
        url = (
            path
            if "://" in path
            else definition.base_url.rstrip("/") + "/" + path.lstrip("/")
        )
        headers = {name: fill(value) for name, value in step.headers.items()}
        headers.update(self._auth_headers(step.auth, sanitizer))
        return PreparedRequest(
            step.method.upper(),
            url,
            headers,
            {name: fill(str(value)) for name, value in step.params.items()},
            fill_any(step.json),
            fill(step.body) if step.body is not None else None,
            definition.timeout_seconds,
        )

    def _auth_headers(self, auth: AuthSpec, sanitizer: Sanitizer) -> dict[str, str]:
        if auth.kind == "none":
            return {}

        def secret(name: str) -> str:
            value = self._environment.get(name)
            if not value:
                raise ApiError(
                    f"Environment variable {name} is not set, so the "
                    f"{auth.kind} credential cannot be built."
                )
            sanitizer.add_secret(value)
            return value

        if auth.kind == "bearer":
            token = secret(auth.env)
            return {"Authorization": f"Bearer {token}"}
        if auth.kind == "basic":
            user, password = secret(auth.user_env), secret(auth.env)
            encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
            sanitizer.add_secret(encoded)
            return {"Authorization": f"Basic {encoded}"}
        return {auth.header: secret(auth.env)}

    # -- checking ------------------------------------------------------------

    def _check(
        self,
        expect: Expectation,
        response: TransportResponse,
        sanitizer: Sanitizer,
    ) -> tuple[list[CheckResult], Any]:
        checks: list[CheckResult] = []
        text = response.body.decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(text) if text.strip() else None
            is_json = text.strip() != ""
        except ValueError:
            parsed, is_json = None, False

        if expect.status:
            ok = response.status in expect.status
            checks.append(
                CheckResult(
                    "status",
                    ok,
                    f"got {response.status}, expected "
                    f"{' or '.join(map(str, expect.status))}",
                )
            )
        if expect.max_ms is not None:
            ok = response.elapsed_ms <= expect.max_ms
            checks.append(
                CheckResult(
                    "response time",
                    ok,
                    f"{response.elapsed_ms:.0f} ms, limit {expect.max_ms:g} ms",
                )
            )
        for name, wanted in expect.headers.items():
            actual = {k.lower(): v for k, v in response.headers.items()}.get(
                name.lower()
            )
            checks.append(
                CheckResult(
                    f"header {name}",
                    actual == wanted,
                    f"got {sanitizer.text(str(actual))!r}, expected {wanted!r}",
                )
            )
        if expect.contains is not None:
            checks.append(
                CheckResult(
                    "body contains",
                    expect.contains in text,
                    f"text {sanitizer.text(expect.contains)!r}",
                )
            )
        needs_json = expect.json_schema is not None or expect.json_equals
        if needs_json and not is_json:
            checks.append(CheckResult("json body", False, "the response is not JSON"))
            return checks, None
        if expect.json_schema is not None:
            errors = sorted(
                jsonschema.Draft202012Validator(expect.json_schema).iter_errors(parsed),
                key=lambda e: list(e.path),
            )
            detail = "; ".join(
                f"{'/'.join(map(str, e.path)) or '(root)'}: {sanitizer.text(e.message)}"
                for e in errors[:5]
            )
            checks.append(CheckResult("json schema", not errors, detail))
        for path, wanted in expect.json_equals.items():
            try:
                actual = read_path(parsed, path)
            except KeyError as error:
                checks.append(CheckResult(f"json {path}", False, str(error)))
                continue
            checks.append(
                CheckResult(
                    f"json {path}",
                    actual == wanted,
                    f"got {sanitizer.value(actual)!r}, "
                    f"expected {sanitizer.value(wanted)!r}",
                )
            )
        return checks, parsed

    def _extract(
        self,
        step: ApiStep,
        parsed: Any,
        variables: dict[str, str],
        sanitizer: Sanitizer,
    ) -> None:
        for name, extract in step.extract.items():
            try:
                value = read_path(parsed, extract.path)
            except KeyError as error:
                raise ApiError(f"Cannot extract {name!r}: {error}") from error
            text = value if isinstance(value, str) else json.dumps(value)
            variables[name] = text
            if extract.secret:
                sanitizer.add_secret(text)

    # -- logging -------------------------------------------------------------

    @staticmethod
    def _exchange(
        request: PreparedRequest,
        response: TransportResponse | None,
        sanitizer: Sanitizer,
    ) -> Exchange:
        if request.json is not None:
            request_body = sanitizer.body(json.dumps(request.json))
        else:
            request_body = sanitizer.body(request.body)
        url = sanitizer.url(request.url)
        if request.params:
            url += (" ?" if "?" not in url else " &") + "&".join(
                f"{k}={v}" for k, v in sanitizer.params(request.params).items()
            )
        return Exchange(
            request.method,
            url,
            sanitizer.headers(request.headers),
            request_body,
            response.status if response else None,
            sanitizer.headers(response.headers) if response else {},
            sanitizer.body(response.body) if response else "",
            response.elapsed_ms if response else None,
        )
