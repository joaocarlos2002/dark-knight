import threading
import time

import pytest
from fake_ai import FakeHttp, down, ok

from qa_workbench.ai.contract import (
    CancelToken,
    CompletionRequest,
    Message,
    ToolSpec,
)
from qa_workbench.ai.errors import (
    CapabilityNotSupported,
    ProviderCancelled,
    ProviderResponseError,
    ProviderUnavailable,
)
from qa_workbench.ai.opencode import OpenCodeProvider

URL = "http://127.0.0.1:4096"
REPLY = {"info": {}, "parts": [{"type": "text", "text": '{"statements": []}'}]}


def _request(**fields) -> CompletionRequest:
    messages = (Message("system", "rules"), Message("user", "hi"))
    return CompletionRequest(messages, "anthropic/some-model", **fields)


def _provider(routes, env=None) -> tuple[OpenCodeProvider, FakeHttp]:
    http = FakeHttp(routes)
    return OpenCodeProvider(http, base_url=URL, environment=env or {}), http


def _chat_routes(message):
    return {
        ("POST", "/session"): ok({"id": "ses_1"}),
        ("POST", "/session/ses_1/message"): message,
    }


def test_availability_uses_the_documented_health_endpoint() -> None:
    up, _ = _provider(
        {("GET", "/global/health"): ok({"healthy": True, "version": "1.2.3"})}
    )
    absent, _ = _provider({("GET", "/global/health"): down()})
    locked, _ = _provider({("GET", "/global/health"): ok({}, 401)})
    odd, _ = _provider({("GET", "/global/health"): ok({"healthy": False})})

    assert up.check_availability().version == "1.2.3"
    assert "opencode serve" in absent.check_availability().detail
    assert "OPENCODE_SERVER_PASSWORD" in locked.check_availability().detail
    assert not odd.check_availability().available


def test_basic_auth_comes_from_the_environment_only() -> None:
    env = {"OPENCODE_SERVER_PASSWORD": "pw-123456", "OPENCODE_SERVER_USERNAME": "qa"}
    provider, http = _provider(
        {("GET", "/global/health"): ok({"healthy": True, "version": "1"})}, env
    )

    provider.check_availability()

    assert http.calls[0][3]["Authorization"].startswith("Basic ")
    plain, plain_http = _provider({("GET", "/global/health"): ok({"healthy": True})})
    plain.check_availability()
    assert "Authorization" not in plain_http.calls[0][3]


def test_complete_creates_a_session_and_sends_text_parts_with_model_and_system() -> (
    None
):
    provider, http = _provider(_chat_routes(ok(REPLY)))

    result = provider.complete(_request())

    body = http.calls[1][2]
    assert body["parts"] == [{"type": "text", "text": "user: hi"}]
    assert body["system"] == "rules"
    assert body["model"] == {"providerID": "anthropic", "modelID": "some-model"}
    assert result.text == '{"statements": []}'


def test_unsupported_features_are_refused_not_faked() -> None:
    provider, http = _provider({})
    tool = ToolSpec("t", "d", {"type": "object"})

    with pytest.raises(CapabilityNotSupported, match="tool calls"):
        provider.complete(_request(tools=(tool,)))
    with pytest.raises(CapabilityNotSupported, match="structured"):
        provider.complete(_request(response_schema={"type": "object"}))
    with pytest.raises(CapabilityNotSupported, match="streaming"):
        list(provider.stream(_request()))
    assert http.calls == []


def test_replies_that_do_not_match_the_documented_shape_are_errors() -> None:
    for bad in (ok({"nope": 1}), ok("text"), ok({"parts": [{"type": "tool"}]})):
        provider, _ = _provider(_chat_routes(bad))
        with pytest.raises(ProviderResponseError):
            provider.complete(_request())
    no_id, _ = _provider({("POST", "/session"): ok({})})
    with pytest.raises(ProviderResponseError, match="no session id"):
        no_id.complete(_request())


def test_model_must_name_its_provider() -> None:
    provider, _ = _provider(_chat_routes(ok(REPLY)))

    with pytest.raises(ProviderResponseError, match="provider/model"):
        provider.complete(CompletionRequest((Message("user", "x"),), "justmodel"))


def test_unreachable_and_rejected_credentials_are_unavailable() -> None:
    provider, _ = _provider({("POST", "/session"): down()})
    with pytest.raises(ProviderUnavailable, match="opencode serve"):
        provider.complete(_request())
    rejected, _ = _provider({("POST", "/session"): ok({}, 401)})
    with pytest.raises(ProviderUnavailable, match="credentials"):
        rejected.complete(_request())


def test_cancelling_aborts_the_session_on_the_server() -> None:
    release = threading.Event()

    def slow(body):
        release.wait(5)
        return ok(REPLY)

    provider, http = _provider(
        {**_chat_routes(slow), ("POST", "/session/ses_1/abort"): ok(True)}
    )
    cancel = CancelToken()
    threading.Timer(0.2, cancel.cancel).start()

    started = time.time()
    with pytest.raises(ProviderCancelled):
        provider.complete(_request(), cancel)
    release.set()

    assert time.time() - started < 3
    assert any(url.endswith("/abort") for _, url, _, _ in http.calls)


def test_models_are_listed_as_provider_slash_model() -> None:
    provider, _ = _provider(
        {
            ("GET", "/config/providers"): ok(
                {"providers": [{"id": "anthropic", "models": {"m1": {}, "m2": {}}}]}
            )
        }
    )

    assert provider.list_models() == ["anthropic/m1", "anthropic/m2"]


def test_a_password_kept_with_the_config_command_is_used(monkeypatch, tmp_path) -> None:
    from qa_workbench.security.credentials import CredentialStore

    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
    CredentialStore(tmp_path).set("opencode", "stored-pw-123456")
    http = FakeHttp({("GET", "/global/health"): ok({"healthy": True, "version": "1"})})

    OpenCodeProvider(http, base_url=URL).check_availability()

    assert http.calls[0][3]["Authorization"].startswith("Basic ")


def test_a_damaged_credentials_file_is_reported_not_ignored(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("OPENCODE_SERVER_PASSWORD", raising=False)
    (tmp_path / "credentials.json").write_text("{broken", encoding="utf-8")
    http = FakeHttp({("GET", "/global/health"): ok({"healthy": True})})

    availability = OpenCodeProvider(http, base_url=URL).check_availability()

    assert not availability.available and "credentials file" in availability.detail
    assert http.calls == []
