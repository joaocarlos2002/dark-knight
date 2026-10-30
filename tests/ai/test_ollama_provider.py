import pytest
from fake_ai import FakeHttp, down, lines, ok

from qa_workbench.ai.contract import (
    CancelToken,
    CompletionRequest,
    Message,
    ToolSpec,
)
from qa_workbench.ai.errors import (
    ProviderCancelled,
    ProviderRateLimited,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from qa_workbench.ai.http import TransportFailure
from qa_workbench.ai.ollama import OllamaProvider

URL = "http://127.0.0.1:11434"


def _request(**fields) -> CompletionRequest:
    return CompletionRequest((Message("user", "hi"),), "llama3.2", **fields)


def _provider(routes) -> tuple[OllamaProvider, FakeHttp]:
    http = FakeHttp(routes)
    return OllamaProvider(http, base_url=URL), http


def test_availability_reports_the_version_or_how_to_start_it() -> None:
    up, _ = _provider({("GET", "/api/version"): ok({"version": "0.5.1"})})
    absent, _ = _provider({("GET", "/api/version"): down()})
    other, _ = _provider({("GET", "/api/version"): ok("<html>", 200)})

    assert up.check_availability().version == "0.5.1"
    assert "ollama serve" in absent.check_availability().detail
    assert not other.check_availability().available


def test_lists_installed_models() -> None:
    provider, _ = _provider(
        {("GET", "/api/tags"): ok({"models": [{"name": "llama3.2:latest"}]})}
    )

    assert provider.list_models() == ["llama3.2:latest"]


def test_complete_sends_messages_schema_and_tools_and_reads_the_reply() -> None:
    provider, http = _provider(
        {
            ("POST", "/api/chat"): ok(
                {
                    "model": "llama3.2",
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "get_record",
                                    "arguments": {"id": "TC-1"},
                                }
                            }
                        ],
                    },
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 12,
                    "eval_count": 3,
                }
            )
        }
    )
    schema = {"type": "object"}
    tool = ToolSpec("get_record", "Read", {"type": "object"})

    result = provider.complete(
        _request(tools=(tool,), response_schema=schema, temperature=0)
    )

    body = http.calls[0][2]
    assert body["stream"] is False and body["format"] == schema
    assert body["tools"][0]["function"]["name"] == "get_record"
    assert body["options"] == {"temperature": 0}
    assert result.tool_calls[0].arguments == {"id": "TC-1"}
    assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 3)


def test_streaming_yields_text_then_a_done_event_with_the_whole_result() -> None:
    provider, _ = _provider(
        {
            ("POST", "/api/chat"): lines(
                {"message": {"content": "Hel"}, "done": False},
                {"message": {"content": "lo"}, "done": False},
                {
                    "message": {"content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "eval_count": 2,
                    "model": "llama3.2",
                },
            )
        }
    )

    events = list(provider.stream(_request()))

    assert [e.text for e in events if e.kind == "text"] == ["Hel", "lo"]
    assert events[-1].kind == "done" and events[-1].result.text == "Hello"
    assert events[-1].result.usage.output_tokens == 2


def test_stream_cut_short_is_an_error_not_a_partial_success() -> None:
    provider, _ = _provider(
        {("POST", "/api/chat"): lines({"message": {"content": "Hel"}, "done": False})}
    )

    with pytest.raises(ProviderResponseError, match="before the final message"):
        list(provider.stream(_request()))


def test_stream_can_be_cancelled_midway() -> None:
    provider, _ = _provider(
        {
            ("POST", "/api/chat"): lines(
                {"message": {"content": "a"}, "done": False},
                {"message": {"content": "b"}, "done": False},
            )
        }
    )
    cancel = CancelToken()
    events = provider.stream(_request(), cancel)

    assert next(events).text == "a"
    cancel.cancel()
    with pytest.raises(ProviderCancelled):
        next(events)


def test_failures_are_distinct_and_explicit() -> None:
    cases = {
        TransportFailure("timeout", "slow"): ProviderTimeout,
        TransportFailure("connection", "refused"): ProviderUnavailable,
    }
    for failure, expected in cases.items():
        provider, _ = _provider({("POST", "/api/chat"): failure})
        with pytest.raises(expected):
            provider.complete(_request())

    missing, _ = _provider(
        {("POST", "/api/chat"): ok({"error": "model not found"}, 404)}
    )
    with pytest.raises(ProviderResponseError, match="ollama pull"):
        missing.complete(_request())
    limited, _ = _provider({("POST", "/api/chat"): ok({}, 429)})
    with pytest.raises(ProviderRateLimited):
        limited.complete(_request())
    erroring, _ = _provider({("POST", "/api/chat"): ok({"error": "out of memory"})})
    with pytest.raises(ProviderResponseError, match="out of memory"):
        erroring.complete(_request())
    shapeless, _ = _provider({("POST", "/api/chat"): ok({"done": True})})
    with pytest.raises(ProviderResponseError, match="no message"):
        shapeless.complete(_request())


def test_a_request_without_a_model_is_refused_before_sending() -> None:
    provider, http = _provider({})

    with pytest.raises(ProviderResponseError, match="no model"):
        provider.complete(CompletionRequest((Message("user", "hi"),)))
    assert http.calls == []


def test_malformed_tool_calls_are_errors() -> None:
    bad = ok(
        {"message": {"content": "", "tool_calls": [{"function": {}}]}, "done": True}
    )
    provider, _ = _provider({("POST", "/api/chat"): bad})

    with pytest.raises(ProviderResponseError, match="no name"):
        provider.complete(_request())
