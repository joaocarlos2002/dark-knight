"""Alfred: the workbench's QA assistant, its settings, and how a question is asked.

Alfred is a thin layer over the engines of :mod:`qa_workbench.ai`: it picks an
engine (``own``, ``opencode``, or ``auto``), gives the agent read-only tools over
the project's records, attaches the records a question mentions (``@REQ-001``),
and applies a style preference. The rules never change: a fact needs a source the
agent really saw, and nothing the assistant says is evidence.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from qa_workbench.ai import ollama, opencode
from qa_workbench.ai.agent import AgentAnswer, OwnAgent, SingleShotAgent
from qa_workbench.ai.cli import record_tools
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.http import JsonHttp
from qa_workbench.ai.selection import MODES, select_engine
from qa_workbench.storage.atomic import write_text_atomic
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository

SETTINGS_PATH = ("ai", "alfred.yaml")
STYLES = {
    "balanced": "",
    "concise": "Answer in at most five short statements.",
    "detailed": "Explain the reasoning briefly and cite the record behind each fact.",
}
MENTION = re.compile(r"@([A-Z]{2,6}(?:-EXEC)?-\d{3,})")
MAX_CONTEXT_CHARS = 6000


class AlfredSettingsError(ValueError):
    """The assistant settings are invalid."""


@dataclass(frozen=True)
class AlfredSettings:
    engine: str = "auto"
    model: str = ""
    style: str = "balanced"
    language: str = ""
    ollama_url: str = ollama.DEFAULT_URL
    opencode_url: str = opencode.DEFAULT_URL

    def __post_init__(self) -> None:
        problems = []
        if self.engine not in MODES:
            problems.append(f"engine must be one of {', '.join(MODES)}")
        if self.style not in STYLES:
            problems.append(f"style must be one of {', '.join(STYLES)}")
        for name, url in (
            ("ollama_url", self.ollama_url),
            ("opencode_url", self.opencode_url),
        ):
            if not url.startswith(("http://", "https://")):
                problems.append(f"{name} must start with http:// or https://")
        if problems:
            raise AlfredSettingsError("; ".join(problems))

    @property
    def style_instruction(self) -> str:
        parts = [STYLES[self.style]]
        if self.language.strip():
            parts.append(f"Answer in {self.language.strip()}.")
        return " ".join(part for part in parts if part)


def settings_file(project_root: Path) -> Path:
    return project_root.joinpath(*SETTINGS_PATH)


def load_settings(project_root: Path) -> AlfredSettings:
    """Saved settings; none saved means the defaults, a broken file is an error."""
    path = settings_file(project_root)
    if not path.is_file():
        return AlfredSettings()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("it must contain a mapping")
        return AlfredSettings(**{k: str(v) for k, v in data.items()})
    except (OSError, yaml.YAMLError, ValueError, TypeError) as error:
        raise AlfredSettingsError(f"Cannot read {path}: {error}") from error


def save_settings(project_root: Path, settings: AlfredSettings) -> None:
    path = settings_file(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, yaml.safe_dump(settings.__dict__, sort_keys=False))


@dataclass(frozen=True)
class Reply:
    answer: AgentAnswer
    engine: str
    attached: tuple[str, ...]
    not_found: tuple[str, ...]


def attach_mentions(
    repository: MarkdownRepository, question: str
) -> tuple[dict[str, str], list[str]]:
    """Records the question names with ``@ID``: (id -> text, ids not found)."""
    context: dict[str, str] = {}
    missing: list[str] = []
    for record_id in dict.fromkeys(MENTION.findall(question)):
        try:
            record = repository.get(record_id)
        except (StorageError, KeyError, ValueError):
            missing.append(record_id)
            continue
        context[record_id] = record.body.strip()[:MAX_CONTEXT_CHARS]
    return context, missing


def ask_alfred(
    settings: AlfredSettings,
    repository: MarkdownRepository,
    http: JsonHttp,
    question: str,
) -> Reply:
    """Ask once. Raises :class:`NoProviderAvailable` or a ``ProviderError``."""
    if not question.strip():
        raise ValueError("Ask something.")
    context, missing = attach_mentions(repository, question)
    tools = record_tools(repository)
    style = settings.style_instruction

    def own():
        provider = ollama.OllamaProvider(
            http, base_url=settings.ollama_url, model=settings.model
        )
        return provider, OwnAgent(provider, tools, model=settings.model, style=style)

    def external():
        provider = opencode.OpenCodeProvider(
            http, base_url=settings.opencode_url, model=settings.model
        )
        return provider, SingleShotAgent(provider, model=settings.model, style=style)

    choice = select_engine(settings.engine, {"own": own, "opencode": external})
    answer = choice.engine.ask(question, context)
    return Reply(answer, choice.mode, tuple(context), tuple(missing))


def format_answer(reply: Reply) -> list[str]:
    """The reply as lines: each statement tagged with what kind of claim it is."""
    lines = []
    for statement in reply.answer.statements:
        sources = f" [{', '.join(statement.sources)}]" if statement.sources else ""
        note = "  (claimed as a fact without a source)" if statement.demoted else ""
        lines.append(f"{statement.kind.upper():<14} {statement.text}{sources}{note}")
    return lines


__all__ = [
    "AlfredSettings",
    "AlfredSettingsError",
    "NoProviderAvailable",
    "ProviderError",
    "Reply",
    "STYLES",
    "ask_alfred",
    "attach_mentions",
    "format_answer",
    "load_settings",
    "save_settings",
]
