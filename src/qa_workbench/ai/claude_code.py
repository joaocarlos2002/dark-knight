"""The Claude Code adapter: Claude through the CLI the person already signed in to.

It runs ``claude -p`` (print mode) as a child process, so it uses the person's own
Claude login and needs no API key. The prompt goes through standard input, not the
command line. Claude Code is started with every tool disabled, no saved session, no
skills or slash commands, and no MCP servers, in an empty temporary directory, so
the model can only answer: it cannot read files, run commands, or change anything
on this machine. This adapter offers no workbench tool calls or structured output
and says so (:class:`CapabilityNotSupported`) instead of faking them.

The model runs on Anthropic's servers, so this is a *remote* engine: ``auto`` never
picks it, the UI says data leaves the machine, message text is passed through
``redact_secrets`` first, and the process only starts if the action guard allows
``api.anthropic.com`` for the project (see :mod:`.guarded`).

Compatibility: written against Claude Code 2.1 (October 2026), using its documented
options ``-p``, ``--output-format json``, ``--tools``, ``--system-prompt``,
``--model``, ``--no-session-persistence``, ``--disable-slash-commands`` and
``--strict-mcp-config``. A reply without the documented ``result`` field is an
explicit error.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from qa_workbench.ai.contract import (
    Availability,
    CancelToken,
    Capabilities,
    CompletionRequest,
    CompletionResult,
    StreamEvent,
    Usage,
)
from qa_workbench.ai.errors import (
    CapabilityNotSupported,
    ProviderCancelled,
    ProviderResponseError,
    ProviderTimeout,
    ProviderUnavailable,
)
from qa_workbench.core.secrets import redact_secrets

NAME = "claude"
HOST_URL = "https://api.anthropic.com"
PATH_VARIABLE = "CLAUDE_CODE_PATH"
# Model aliases the CLI accepts; a full model id works too.
MODELS = ("sonnet", "opus", "haiku")
_MAX_DETAIL = 300
_LOGIN_HINT = "Open `claude` once in a terminal and sign in, then try again"


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    """Starts the CLI. ``run`` sends the person's text off the machine and is the
    one the action guard wraps; ``probe`` only asks the CLI about itself."""

    def run(
        self,
        args: list[str],
        stdin: str,
        timeout: float,
        cancel: CancelToken | None = None,
    ) -> ProcessResult: ...

    def probe(self, args: list[str]) -> ProcessResult: ...


class SubprocessRunner:
    """The real runner. Tests replace it so no process is started."""

    def run(self, args, stdin, timeout, cancel=None):
        with tempfile.TemporaryDirectory(prefix="batman-claude-") as empty:
            try:
                process = subprocess.Popen(  # noqa: S603 - args are built, not shell
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=empty,
                )
            except OSError as error:
                raise ProviderUnavailable(
                    NAME, f"cannot start Claude Code ({type(error).__name__})"
                ) from error
            deadline = time.monotonic() + timeout
            pending: str | None = stdin
            while True:
                try:
                    out, err = process.communicate(pending, timeout=0.2)
                    return ProcessResult(process.returncode, out, err)
                except subprocess.TimeoutExpired:
                    pending = None  # already written; keep waiting for the output
                if cancel is not None and cancel.cancelled:
                    process.kill()
                    process.communicate()
                    raise ProviderCancelled(NAME, "the request was cancelled")
                if time.monotonic() > deadline:
                    process.kill()
                    process.communicate()
                    raise ProviderTimeout(
                        NAME,
                        f"Claude Code gave no answer in {timeout:g}s",
                        hint="Raise the timeout",
                    )

    def probe(self, args):
        try:
            done = subprocess.run(  # noqa: S603 - args are built, not shell
                args,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProviderUnavailable(
                NAME, f"cannot start Claude Code ({type(error).__name__})"
            ) from error
        return ProcessResult(done.returncode, done.stdout, done.stderr)


def find_claude(environment: Mapping[str, str] | None = None) -> str | None:
    """Where the Claude Code CLI is: the configured path, ``claude`` on the PATH,
    or the copy that ships inside the VS Code extension. ``None`` if not found."""
    env = os.environ if environment is None else environment
    configured = env.get(PATH_VARIABLE, "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    found = shutil.which("claude")
    if found:
        return found
    home = Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    pattern = str(
        home
        / ".vscode"
        / "extensions"
        / "anthropic.claude-code-*"
        / "resources"
        / "native-binary"
        / "claude*"
    )
    candidates = sorted(
        (p for p in glob.glob(pattern) if Path(p).stem == "claude"), reverse=True
    )
    return candidates[0] if candidates else None


def _flags(system: str, model: str) -> list[str]:
    flags = [
        "-p",
        "--output-format",
        "json",
        "--tools",
        "",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--system-prompt",
        system or "Answer the user.",
    ]
    if model:
        flags += ["--model", model]
    return flags


class ClaudeCodeProvider:
    name = NAME
    capabilities = Capabilities(lists_models=True)

    def __init__(
        self,
        runner: Runner,
        *,
        model: str = "",
        executable: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._runner = runner
        self._model = model
        self._executable = executable
        self._environment = environment

    def _binary(self) -> str:
        path = self._executable or find_claude(self._environment)
        if not path:
            raise ProviderUnavailable(
                NAME,
                "Claude Code was not found",
                hint=f"Install it, or set {PATH_VARIABLE} to the claude executable",
            )
        return path

    # -- availability --------------------------------------------------------

    def check_availability(self) -> Availability:
        try:
            result = self._runner.probe([self._binary(), "--version"])
        except ProviderUnavailable as error:
            return Availability(False, str(error))
        version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if result.returncode != 0 or not version:
            return Availability(False, "Claude Code did not report its version.")
        return Availability(
            True,
            f"{version} (remote: sends text to Anthropic with your Claude login)",
            version,
        )

    def list_models(self) -> list[str]:
        return list(MODELS)

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
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        prompt = "\n\n".join(
            f"{m.role}: {m.content}" for m in request.messages if m.role != "system"
        )
        args = [self._binary(), *_flags(redact_secrets(system), model)]
        if cancel is not None and cancel.cancelled:
            raise ProviderCancelled(NAME, "the request was cancelled")
        result = self._runner.run(
            args, redact_secrets(prompt), request.timeout_seconds, cancel
        )
        return self._result(result, model)

    def stream(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> Iterator[StreamEvent]:
        raise CapabilityNotSupported(NAME, "streaming is not supported; use complete()")

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _detail(text: str) -> str:
        return redact_secrets(text).strip()[:_MAX_DETAIL]

    def _result(self, result: ProcessResult, model: str) -> CompletionResult:
        body: Any = None
        try:
            body = json.loads(result.stdout) if result.stdout.strip() else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            detail = self._detail(result.stderr or result.stdout)
            raise ProviderResponseError(
                NAME,
                f"Claude Code failed (exit {result.returncode})"
                + (f": {detail}" if detail else ""),
                hint=_LOGIN_HINT,
            )
        text = body.get("result")
        if body.get("is_error") or result.returncode != 0:
            detail = self._detail(str(text or result.stderr))
            raise ProviderResponseError(
                NAME,
                "Claude Code reported an error" + (f": {detail}" if detail else ""),
                hint=_LOGIN_HINT,
            )
        if not isinstance(text, str) or not text.strip():
            raise ProviderResponseError(
                NAME,
                "the reply has no result text",
                hint="The Claude Code version may be incompatible",
            )
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        used = body.get("modelUsage")
        shown = next(iter(used), "") if isinstance(used, dict) and used else ""
        return CompletionResult(
            text,
            model or shown,
            finish_reason=str(body.get("stop_reason") or ""),
            usage=Usage(usage.get("input_tokens"), usage.get("output_tokens")),
        )
