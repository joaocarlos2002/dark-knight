"""Loading API test definitions from YAML."""

from pathlib import Path
from typing import Any

import yaml

from qa_workbench.api.errors import ApiDefinitionError
from qa_workbench.api.models import (
    AUTH_KINDS,
    METHODS,
    ApiDefinition,
    ApiStep,
    AuthSpec,
    Expectation,
    Extract,
)
from qa_workbench.core.secrets import find_secrets


def load_definition(path: Path) -> ApiDefinition:
    """Read a definition file; every problem found is reported together."""
    try:
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except (OSError, yaml.YAMLError) as error:
        raise ApiDefinitionError(f"Cannot read {path}: {error}") from error
    problems = [
        f"the file contains {leak}; use an environment variable"
        for leak in dict.fromkeys(_literal_secrets(data))
    ]
    definition = parse_definition(data, problems)
    if problems:
        listed = "\n".join(f"  - {problem}" for problem in problems)
        raise ApiDefinitionError(f"{path} is not a valid API test:\n{listed}")
    assert definition is not None
    return definition


def _literal_secrets(data: Any, key: str = "") -> list[str]:
    """Credentials written into the file, found in its values (not key names)."""
    if isinstance(data, dict):
        return [leak for k, v in data.items() for leak in _literal_secrets(v, str(k))]
    if isinstance(data, list):
        return [leak for item in data for leak in _literal_secrets(item, key)]
    if isinstance(data, str):
        return find_secrets(data) + (find_secrets(f"{key}={data}") if key else [])
    return []


def _as_dict(value: Any, where: str, problems: list[str]) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    problems.append(f"{where} must be a mapping.")
    return {}


def parse_definition(data: Any, problems: list[str]) -> ApiDefinition | None:
    if not isinstance(data, dict):
        problems.append("the document must be a mapping.")
        return None
    name = str(data.get("name", "")).strip()
    base_url = str(data.get("base_url", "")).strip()
    if not name:
        problems.append("name is required.")
    if not base_url.startswith(("http://", "https://")):
        problems.append("base_url must start with http:// or https://.")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        problems.append("steps must be a non-empty list.")
        raw_steps = []
    steps = tuple(
        step
        for index, raw in enumerate(raw_steps, start=1)
        if (step := _parse_step(raw, index, problems)) is not None
    )
    names = [step.name for step in steps]
    for duplicate in sorted({n for n in names if names.count(n) > 1}):
        problems.append(f"step name {duplicate!r} is used more than once.")
    timeout = data.get("timeout_seconds", 30)
    if not isinstance(timeout, int | float) or timeout <= 0:
        problems.append("timeout_seconds must be a positive number.")
        timeout = 30
    return ApiDefinition(
        name, base_url, steps, float(timeout), bool(data.get("stop_on_failure", True))
    )


def _parse_step(raw: Any, index: int, problems: list[str]) -> ApiStep | None:
    where = f"step {index}"
    if not isinstance(raw, dict):
        problems.append(f"{where} must be a mapping.")
        return None
    name = str(raw.get("name", "")).strip()
    where = f"step {index} ({name or 'unnamed'})"
    if not name:
        problems.append(f"{where}: name is required.")
    method = str(raw.get("method", "GET")).upper()
    if method not in METHODS:
        problems.append(f"{where}: method {method!r} is not one of {sorted(METHODS)}.")
    url = str(raw.get("url", "")).strip()
    if not url:
        problems.append(f"{where}: url is required.")
    if "json" in raw and "body" in raw:
        problems.append(f"{where}: use either json or body, not both.")
    auth = _parse_auth(raw.get("auth"), where, problems)
    expect = _parse_expect(raw.get("expect"), where, problems)
    extract: dict[str, Extract] = {}
    for key, spec in _as_dict(
        raw.get("extract"), f"{where}: extract", problems
    ).items():
        if isinstance(spec, str):
            extract[key] = Extract(spec)
        elif isinstance(spec, dict) and isinstance(spec.get("path"), str):
            extract[key] = Extract(spec["path"], bool(spec.get("secret", False)))
        else:
            problems.append(f"{where}: extract {key!r} needs a '$.path'.")
    return ApiStep(
        name,
        method,
        url,
        {
            k: str(v)
            for k, v in _as_dict(
                raw.get("path_params"), f"{where}: path_params", problems
            ).items()
        },
        {
            k: str(v)
            for k, v in _as_dict(
                raw.get("params"), f"{where}: params", problems
            ).items()
        },
        {
            k: str(v)
            for k, v in _as_dict(
                raw.get("headers"), f"{where}: headers", problems
            ).items()
        },
        raw.get("json"),
        raw.get("body"),
        auth,
        expect,
        extract,
    )


def _parse_auth(raw: Any, where: str, problems: list[str]) -> AuthSpec:
    if raw is None:
        return AuthSpec()
    if not isinstance(raw, dict):
        problems.append(f"{where}: auth must be a mapping.")
        return AuthSpec()
    kind = str(raw.get("type", "none"))
    if kind not in AUTH_KINDS:
        problems.append(
            f"{where}: auth type {kind!r} is not one of {sorted(AUTH_KINDS)}."
        )
    auth = AuthSpec(
        kind,
        str(raw.get("env", "")),
        str(raw.get("user_env", "")),
        str(raw.get("header", "")),
    )
    if kind != "none" and not auth.env:
        problems.append(
            f"{where}: auth needs 'env', the name of the environment variable."
        )
    if kind == "basic" and not auth.user_env:
        problems.append(f"{where}: basic auth needs 'user_env'.")
    if kind == "header" and not auth.header:
        problems.append(f"{where}: header auth needs 'header', the header name.")
    return auth


def _parse_expect(raw: Any, where: str, problems: list[str]) -> Expectation:
    data = _as_dict(raw, f"{where}: expect", problems)
    status = data.get("status", ())
    if isinstance(status, int):
        status = (status,)
    if not isinstance(status, list | tuple) or not all(
        isinstance(s, int) for s in status
    ):
        problems.append(
            f"{where}: expect.status must be a number or a list of numbers."
        )
        status = ()
    max_ms = data.get("max_ms")
    if max_ms is not None and (not isinstance(max_ms, int | float) or max_ms <= 0):
        problems.append(f"{where}: expect.max_ms must be a positive number.")
        max_ms = None
    schema = data.get("json_schema")
    if schema is not None:
        if not isinstance(schema, dict):
            problems.append(f"{where}: expect.json_schema must be a mapping.")
            schema = None
        else:
            import jsonschema

            try:
                jsonschema.Draft202012Validator.check_schema(schema)
            except jsonschema.SchemaError as error:
                problems.append(
                    f"{where}: expect.json_schema is invalid: {error.message}"
                )
                schema = None
    return Expectation(
        tuple(status),
        float(max_ms) if max_ms is not None else None,
        schema,
        _as_dict(data.get("json_equals"), f"{where}: expect.json_equals", problems),
        data.get("contains"),
        {
            k: str(v)
            for k, v in _as_dict(
                data.get("headers"), f"{where}: expect.headers", problems
            ).items()
        },
    )
