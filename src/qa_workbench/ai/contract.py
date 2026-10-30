"""The contract every AI provider implements (spec 7.1).

QA modules depend on this file only, never on a particular provider.
"""

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

ROLES = ("system", "user", "assistant", "tool")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_name: str = ""

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, got {self.role!r}")


@dataclass(frozen=True)
class CompletionRequest:
    messages: tuple[Message, ...]
    model: str = ""
    tools: tuple[ToolSpec, ...] = ()
    response_schema: dict[str, Any] | None = None
    timeout_seconds: float = 120.0
    temperature: float | None = None


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str = ""
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True)
class StreamEvent:
    """``kind`` is ``text`` (a piece of the answer), ``tool_call``, or ``done``."""

    kind: str
    text: str = ""
    tool_call: ToolCall | None = None
    result: CompletionResult | None = None


@dataclass(frozen=True)
class Capabilities:
    streaming: bool = False
    tools: bool = False
    structured_output: bool = False
    lists_models: bool = False


@dataclass(frozen=True)
class Availability:
    available: bool
    detail: str
    version: str = ""


class CancelToken:
    """Lets another thread cancel a running request."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class Provider(Protocol):
    name: str
    capabilities: Capabilities

    def check_availability(self) -> Availability: ...

    def list_models(self) -> list[str]: ...

    def complete(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> CompletionResult: ...

    def stream(
        self, request: CompletionRequest, cancel: CancelToken | None = None
    ) -> Iterator[StreamEvent]: ...
