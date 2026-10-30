from fake_transport import FakeTransport, reply, unreachable

from qa_workbench.api.models import (
    ApiDefinition,
    ApiStep,
    AuthSpec,
    Expectation,
    Extract,
)
from qa_workbench.api.runner import ApiRunner, read_path
from qa_workbench.api.transport import PreparedRequest

BASE = "https://api.test"


def _flow(*steps: ApiStep, **options: object) -> ApiDefinition:
    return ApiDefinition("Flow", BASE, steps, **options)  # type: ignore[arg-type]


def _step(name: str = "s", **fields: object) -> ApiStep:
    return ApiStep(name, fields.pop("method", "GET"), fields.pop("url", "/x"), **fields)  # type: ignore[arg-type]


def _run(handler, *steps: ApiStep, env: dict[str, str] | None = None, **options):
    transport = FakeTransport(handler)
    runner = ApiRunner(transport, environment=env or {})
    return runner.run(_flow(*steps, **options)), transport


def test_passing_step_checks_status_time_schema_and_values() -> None:
    expect = Expectation(
        status=(200,),
        max_ms=100,
        json_schema={"type": "object", "required": ["id"]},
        json_equals={"$.user.name": "ada", "$.tags[1]": "b"},
        contains="ada",
        headers={"content-type": "application/json"},
    )
    flow, _ = _run(
        lambda r: reply(200, {"id": 1, "user": {"name": "ada"}, "tags": ["a", "b"]}),
        _step(expect=expect),
    )

    assert flow.status == "passed"
    assert all(check.passed for check in flow.steps[0].checks)


def test_each_failed_rule_is_reported_with_detail() -> None:
    expect = Expectation(
        status=(201,),
        max_ms=5,
        json_schema={"type": "object", "required": ["id"]},
        json_equals={"$.a": 2, "$.missing": 1},
    )
    flow, _ = _run(lambda r: reply(200, {"a": 1}, elapsed_ms=50), _step(expect=expect))

    step = flow.steps[0]
    failed = {c.name: c.detail for c in step.checks if not c.passed}
    assert flow.status == "failed" and step.status == "failed"
    assert "got 200" in failed["status"]
    assert "limit 5 ms" in failed["response time"]
    assert "id" in failed["json schema"]
    assert "got 1" in failed["json $.a"] and "not found" in failed["json $.missing"]


def test_json_rules_on_a_non_json_body_fail_clearly() -> None:
    flow, _ = _run(
        lambda r: reply(200, b"<html>"),
        _step(expect=Expectation(json_equals={"$.a": 1})),
    )

    assert flow.steps[0].checks[0].detail == "the response is not JSON"


def test_connection_failure_is_an_error_not_a_pass() -> None:
    flow, _ = _run(unreachable, _step())

    assert flow.status == "error"
    assert "connection refused" in flow.steps[0].error


def test_bearer_token_is_sent_but_never_recorded() -> None:
    flow, transport = _run(
        lambda r: reply(200, {"echo": "Bearer tok-1234567890abcdef"}),
        _step(auth=AuthSpec("bearer", env="API_TOKEN")),
        env={"API_TOKEN": "tok-1234567890abcdef"},
    )

    assert transport.requests[0].headers["Authorization"] == (
        "Bearer tok-1234567890abcdef"
    )
    saved = repr(flow)
    assert "tok-1234567890abcdef" not in saved
    assert flow.steps[0].exchange.request_headers["Authorization"] == "[REDACTED]"  # type: ignore[union-attr]


def test_basic_and_header_auth_are_built_from_the_environment() -> None:
    env = {"U": "ada", "P": "lovelace-pw", "K": "key-value-1"}
    flow, transport = _run(
        lambda r: reply(200, {}),
        _step("basic", auth=AuthSpec("basic", env="P", user_env="U")),
        _step("key", auth=AuthSpec("header", env="K", header="X-Token")),
        env=env,
    )

    assert transport.requests[0].headers["Authorization"].startswith("Basic ")
    assert transport.requests[1].headers["X-Token"] == "key-value-1"
    assert "lovelace-pw" not in repr(flow) and "key-value-1" not in repr(flow)


def test_missing_credential_variable_is_an_explicit_error_and_nothing_is_sent() -> None:
    flow, transport = _run(
        lambda r: reply(200, {}), _step(auth=AuthSpec("bearer", env="NOPE"))
    )

    assert flow.steps[0].status == "error" and "NOPE" in flow.steps[0].error
    assert transport.requests == []


def test_chained_flow_carries_values_and_hides_secret_ones() -> None:
    def handler(request: PreparedRequest):
        if request.url.endswith("/login"):
            return reply(200, {"session": {"value": "opaque-session-9876"}, "id": 7})
        assert request.headers["X-Session"] == "opaque-session-9876"
        assert request.url.endswith("/users/7")
        return reply(200, {"you": "opaque-session-9876"})

    flow, _ = _run(
        handler,
        ApiStep(
            "login",
            "POST",
            "/login",
            json={"user": "ada"},
            extract={
                "sid": Extract("$.session.value", secret=True),
                "uid": Extract("$.id"),
            },
        ),
        ApiStep(
            "profile",
            "GET",
            "/users/{{uid}}",
            headers={"X-Session": "{{sid}}"},
        ),
    )

    assert flow.status == "passed"
    assert "opaque-session-9876" not in repr(flow)


def test_unknown_variable_is_an_error_before_sending() -> None:
    flow, transport = _run(lambda r: reply(200, {}), _step(url="/users/{{nope}}"))

    assert flow.steps[0].status == "error" and "nope" in flow.steps[0].error
    assert transport.requests == []


def test_extracting_a_missing_value_fails_the_step() -> None:
    flow, _ = _run(
        lambda r: reply(200, {"a": 1}),
        _step(extract={"x": Extract("$.zzz")}),
    )

    assert flow.steps[0].status == "failed"
    assert flow.steps[0].checks[-1].name == "extract values"


def test_failure_skips_later_steps_unless_told_otherwise() -> None:
    bad = _step("one", expect=Expectation(status=(500,)))
    later = _step("two")

    stopped, transport = _run(lambda r: reply(200, {}), bad, later)
    continued, _ = _run(lambda r: reply(200, {}), bad, later, stop_on_failure=False)

    assert [s.status for s in stopped.steps] == ["failed", "skipped"]
    assert len(transport.requests) == 1
    assert [s.status for s in continued.steps] == ["failed", "passed"]


def test_path_params_query_params_and_body_reach_the_transport() -> None:
    flow, transport = _run(
        lambda r: reply(201, {}),
        ApiStep(
            "create",
            "POST",
            "/orgs/{org}/users",
            path_params={"org": "acme"},
            params={"dry": "1"},
            json={"name": "ada"},
        ),
    )

    request = transport.requests[0]
    assert request.url == "https://api.test/orgs/acme/users"
    assert request.params == {"dry": "1"} and request.json == {"name": "ada"}
    assert flow.steps[0].exchange.request_body.count("ada") == 1  # type: ignore[union-attr]


def test_read_path_supports_keys_and_indexes() -> None:
    data = {"a": [{"b": 5}]}

    assert read_path(data, "$.a[0].b") == 5
    assert read_path(data, "$") == data
    for bad in ("a.b", "$.zz", "$.a[3]", "$.a..b"):
        try:
            read_path(data, bad)
        except KeyError:
            continue
        raise AssertionError(f"{bad} should have failed")
