"""Choosing the engine: ``own``, ``opencode``, a remote one, or ``auto`` (spec 7.1)."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from qa_workbench.ai.agent import AgentAnswer
from qa_workbench.ai.contract import Provider
from qa_workbench.ai.errors import NoProviderAvailable

MODES = ("own", "opencode", "nvidia", "claude", "auto")
# ``auto`` only prefers engines that run on this machine. A remote engine sends
# data off it, so it is used only when it is asked for by name.
AUTO_ORDER = ("own", "opencode")
REMOTE = frozenset({"nvidia", "claude"})


class Engine(Protocol):
    def ask(
        self, question: str, context: dict[str, str] | None = ..., cancel=...
    ) -> AgentAnswer: ...


@dataclass(frozen=True)
class EngineChoice:
    mode: str  # which engine was chosen: "own", "opencode", "nvidia", or "claude"
    provider: Provider
    engine: Engine
    detail: str


def select_engine(
    mode: str,
    factories: dict[str, Callable[[], tuple[Provider, Engine]]],
) -> EngineChoice:
    """Pick an available engine; say why for each one that is not.

    ``auto`` tries ``own`` then ``opencode`` and takes the first available. It
    never falls back to a different engine when a specific one was requested.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}; got {mode!r}.")
    wanted = AUTO_ORDER if mode == "auto" else (mode,)
    reasons: list[str] = []
    for key in wanted:
        factory = factories.get(key)
        if factory is None:
            reasons.append(f"{key}: not configured")
            continue
        provider, engine = factory()
        availability = provider.check_availability()
        if availability.available:
            return EngineChoice(key, provider, engine, availability.detail)
        reasons.append(f"{key}: {availability.detail}")
    raise NoProviderAvailable("No AI engine is available. " + " | ".join(reasons))
