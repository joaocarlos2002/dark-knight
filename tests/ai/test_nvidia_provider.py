import re

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
    ProviderRateLimited,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from qa_workbench.ai.http import TransportFailure
from qa_workbench.ai.nvidia import NvidiaProvider

URL = "https://nim.example.test/v1"
KEY = "nvapi-0123456789abcdefghij"
REPLY = {
    "model": "meta/llama",
    "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 7, "completion_tokens": 3},
}


def _request(*messages: Message, **fields) -> CompletionRequest:
    return CompletionRequest(
        messages or (Message("user", "hi"),), "meta/llama", **fields
    )


def _provider(routes, env=None) -> tuple[NvidiaProvider, FakeHttp]:
    http = FakeHttp(routes)
    environment = {"NVIDIA_API_KEY": KEY} if env is None else env
    return NvidiaProvider(http, base_url=URL, environment=environment), http


def test_without_a_key_nothing_is_sent_and_the_message_says_how_to_set_it() -> None:
    provider, http = _provider({("GET", "/models"): ok({"data": []})}, env={})

    availability = provider.check_availability()

    assert not availability.available
    assert "batman config token set nvidia" in availability.detail
    assert http.calls == [] and not provider.key_present()


def test_availability_lists_models_with_the_key_in_a_bearer_header() -> None:
    provider, http = _provider(
        {("GET", "/models"): ok({"data": [{"id": "b/m2"}, {"id": "a/m1"}]})}
    )

    availability = provider.check_availability()

    assert availability.available and "2 models" in availability.detail
    assert "remote" in availability.detail and KEY not in availability.detail
    assert http.calls[0][3]["Authorization"] == f"Bearer {KEY}"
    assert provider.list_models() == ["a/m1", "b/m2"]


def test_complete_sends_the_model_and_redacts_secrets_in_messages() -> None:
    provider, http = _provider({("POST", "/chat/completions"): ok(REPLY)})

    result = provider.complete(
        _request(Message("system", "rules"), Message("user", "password=hunter2 ok"))
    )

    body = http.calls[0][2]
    assert body["model"] == "meta/llama" and body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "rules"}
    assert "hunter2" not in body["messages"][1]["content"]
    assert result.text == "hello" and result.finish_reason == "stop"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (7, 3)


def test_the_constructor_model_is_used_when_the_request_has_none() -> None:
    http = FakeHttp({("POST", "/chat/completions"): ok(REPLY)})
    provider = NvidiaProvider(
        http, base_url=URL, model="x/y", environment={"NVIDIA_API_KEY": KEY}
    )

    provider.complete(CompletionRequest((Message("user", "hi"),)))

    assert http.calls[0][2]["model"] == "x/y"


def test_no_model_is_an_explicit_error() -> None:
    provider, http = _provider({})

    with pytest.raises(ProviderResponseError, match="no model") as error:
        provider.complete(CompletionRequest((Message("user", "hi"),)))
    assert "batman ai models" in str(error.value) and http.calls == []


@pytest.mark.parametrize(
    ("response", "kind", "text"),
    [
        (ok({}, 401), ProviderUnavailable, "rejected the API key (HTTP 401)"),
        (ok({}, 403), ProviderUnavailable, "rejected the API key (HTTP 403)"),
        (ok({}, 429), ProviderRateLimited, "rate limited (HTTP 429)"),
        (ok({"detail": "Function not found"}, 404), ProviderResponseError, "model"),
        (ok({"detail": "bad"}, 500), ProviderResponseError, "HTTP 500: bad"),
        (down(), ProviderUnavailable, "cannot reach"),
        (TransportFailure("timeout", "slow"), ProviderTimeout, "no answer in time"),
    ],
)
def test_failures_name_the_endpoint_and_status(response, kind, text) -> None:
    provider, _ = _provider({("POST", "/chat/completions"): response})

    with pytest.raises(kind, match=re.escape(text)) as error:
        provider.complete(_request())

    assert f"{URL}/chat/completions" in str(error.value)
    assert KEY not in str(error.value)


def test_a_server_that_echoes_the_key_does_not_leak_it() -> None:
    provider, _ = _provider(
        {("POST", "/chat/completions"): ok({"detail": f"bad key {KEY}"}, 400)}
    )

    with pytest.raises(ProviderResponseError) as error:
        provider.complete(_request())

    assert KEY not in str(error.value) and "[REDACTED]" in str(error.value)


def test_an_unexpected_reply_shape_is_an_error_not_an_empty_answer() -> None:
    provider, _ = _provider({("POST", "/chat/completions"): ok({"choices": []})})
    with pytest.raises(ProviderResponseError, match="unexpected shape"):
        provider.complete(_request())

    empty = {"choices": [{"message": {"content": "  "}}]}
    provider, _ = _provider({("POST", "/chat/completions"): ok(empty)})
    with pytest.raises(ProviderResponseError, match="no text"):
        provider.complete(_request())


def test_unsupported_features_are_refused_and_cancel_is_honoured() -> None:
    provider, http = _provider({})
    tool = ToolSpec("t", "d", {"type": "object"})

    with pytest.raises(CapabilityNotSupported, match="tool calls"):
        provider.complete(_request(tools=(tool,)))
    with pytest.raises(CapabilityNotSupported, match="structured"):
        provider.complete(_request(response_schema={"type": "object"}))
    with pytest.raises(CapabilityNotSupported, match="streaming"):
        next(provider.stream(_request()))
    token = CancelToken()
    token.cancel()
    with pytest.raises(ProviderCancelled):
        provider.complete(_request(), token)
    assert http.calls == []
