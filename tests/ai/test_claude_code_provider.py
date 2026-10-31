import json
from pathlib import Path

import pytest
from fake_ai import FakeRunner, claude_reply

from qa_workbench.ai.claude_code import (
    ClaudeCodeProvider,
    ProcessResult,
    find_claude,
)
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
from qa_workbench.ai.guarded import GuardedRunner
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.settings import SecuritySettings

EXE = "/opt/claude"


def _request(*messages: Message, **fields) -> CompletionRequest:
    return CompletionRequest(messages or (Message("user", "hi"),), "", **fields)


def _provider(runner: FakeRunner, model: str = "") -> ClaudeCodeProvider:
    return ClaudeCodeProvider(runner, model=model, executable=EXE)


def test_complete_runs_claude_with_every_tool_disabled_and_the_prompt_on_stdin() -> (
    None
):
    runner = FakeRunner(claude_reply("hello"))

    result = _provider(runner, "sonnet").complete(
        _request(Message("system", "rules"), Message("user", "hi there"))
    )

    args, stdin = runner.runs[0]
    assert args[0] == EXE and "-p" in args
    assert args[args.index("--tools") + 1] == ""
    for flag in ("--no-session-persistence", "--disable-slash-commands"):
        assert flag in args
    assert "--strict-mcp-config" in args
    assert args[args.index("--system-prompt") + 1] == "rules"
    assert args[args.index("--model") + 1] == "sonnet"
    assert "hi there" in stdin and "hi there" not in " ".join(args)
    assert result.text == "hello" and result.finish_reason == "end_turn"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (5, 3)


def test_secrets_are_redacted_before_anything_is_sent() -> None:
    runner = FakeRunner(claude_reply("ok"))

    _provider(runner).complete(
        _request(
            Message("system", "token=abc12345"), Message("user", "password=hunter2")
        )
    )

    args, stdin = runner.runs[0]
    assert "hunter2" not in stdin and "abc12345" not in " ".join(args)


def test_no_model_means_the_cli_default() -> None:
    runner = FakeRunner(claude_reply("ok"))

    _provider(runner).complete(_request())

    assert "--model" not in runner.runs[0][0]


def test_a_missing_installation_is_explicit_and_starts_nothing(tmp_path: Path) -> None:
    runner = FakeRunner(claude_reply("x"))
    provider = ClaudeCodeProvider(
        runner, environment={"CLAUDE_CODE_PATH": str(tmp_path / "no")}
    )

    availability = provider.check_availability()
    assert not availability.available and "CLAUDE_CODE_PATH" in availability.detail
    with pytest.raises(ProviderUnavailable, match="not found"):
        provider.complete(_request())
    assert runner.runs == []


def test_availability_reports_the_version_and_that_it_is_remote() -> None:
    availability = _provider(FakeRunner()).check_availability()

    assert availability.available and "2.1.0" in availability.detail
    assert "remote" in availability.detail
    assert not _provider(FakeRunner(version=None)).check_availability().available


@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner("not json", returncode=1, stderr="Not logged in"),
        FakeRunner(json.dumps({"result": "Please log in", "is_error": True})),
        FakeRunner(json.dumps({"is_error": False})),
        FakeRunner(json.dumps({"result": "  "})),
    ],
)
def test_failures_are_explicit_never_an_empty_answer(runner) -> None:
    with pytest.raises(ProviderResponseError):
        _provider(runner).complete(_request())


def test_a_failure_points_to_signing_in_and_does_not_echo_secrets() -> None:
    runner = FakeRunner("", returncode=1, stderr="Not logged in password=hunter2")

    with pytest.raises(ProviderResponseError) as error:
        _provider(runner).complete(_request())

    assert "sign in" in str(error.value) and "hunter2" not in str(error.value)


def test_unsupported_features_are_refused_and_cancel_is_honoured() -> None:
    runner = FakeRunner(claude_reply("x"))
    provider = _provider(runner)
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
    assert runner.runs == []
    assert provider.list_models() == ["sonnet", "opus", "haiku"]


def test_find_claude_prefers_the_configured_path_then_the_vscode_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None)
    configured = tmp_path / "mine.exe"
    configured.write_text("x")
    assert find_claude({"CLAUDE_CODE_PATH": str(configured)}) == str(configured)
    assert find_claude({"CLAUDE_CODE_PATH": str(tmp_path / "gone")}) is None

    for version in ("2.1.9", "2.1.10"):
        binary = (
            (tmp_path / ".vscode" / "extensions" / f"anthropic.claude-code-{version}-x")
            / "resources"
            / "native-binary"
        )
        binary.mkdir(parents=True)
        (binary / "claude.exe").write_text("x")
    found = find_claude({"USERPROFILE": str(tmp_path)})
    assert found is not None and "claude-code-2.1.9" in found  # newest by name sort


def test_the_guard_decides_before_the_process_starts(tmp_path: Path) -> None:
    inner = FakeRunner(claude_reply("ok"))
    audit = AuditLog(tmp_path)

    blocked = GuardedRunner(
        inner, ActionGuard(SecuritySettings(), audit), "https://api.anthropic.com"
    )
    with pytest.raises(ProviderUnavailable, match="nothing was sent") as error:
        blocked.run([EXE, "-p"], "prompt text", 10)
    assert "--allow-host api.anthropic.com" in str(error.value)
    assert inner.runs == []

    allowed = GuardedRunner(
        inner,
        ActionGuard(SecuritySettings(allowed_hosts=("api.anthropic.com",)), audit),
        "https://api.anthropic.com",
    )
    result = allowed.run([EXE, "-p"], "prompt text", 10)
    assert isinstance(result, ProcessResult) and len(inner.runs) == 1
    logged = str([e.data for e in audit.entries()])
    assert "prompt text" not in logged and "run claude" in logged
    # Asking the CLI about itself sends nothing and needs no approval.
    assert allowed.probe([EXE, "--version"]).returncode == 0
