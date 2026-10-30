"""``batman ai`` commands: check the engines and ask a question about a project."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.ai import ollama, opencode
from qa_workbench.ai.agent import (
    AgentAnswer,
    OwnAgent,
    QaTool,
    SingleShotAgent,
    ToolRegistry,
)
from qa_workbench.ai.contract import Provider, ToolSpec
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.http import HttpxJson, JsonHttp
from qa_workbench.ai.selection import MODES, select_engine
from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.workspace import open_repository

ai_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Ask the AI engines about a project. Answers are analysis, not evidence.",
)

OllamaUrl = Annotated[
    str, typer.Option("--ollama-url", envvar="OLLAMA_HOST", help="Ollama server.")
]
OpenCodeUrl = Annotated[
    str, typer.Option("--opencode-url", envvar="OPENCODE_URL", help="opencode serve.")
]


def default_http() -> JsonHttp:
    """The real HTTP client. Tests replace this so nothing touches the network."""
    return HttpxJson()


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def record_tools(repository: MarkdownRepository) -> ToolRegistry:
    """Read-only tools over a project's records."""

    def get_record(arguments: dict) -> str:
        record = repository.get(str(arguments.get("id", "")))
        return f"{record.id} status={record.metadata.get('status')}\n{record.body}"

    def list_records(arguments: dict) -> str:
        listing = repository.list_records(str(arguments.get("prefix", "")))
        return "\n".join(
            f"{r.id} {r.metadata.get('status')} {r.metadata.get('title', '')}"
            for r in listing.records
        )

    return ToolRegistry(
        [
            QaTool(
                ToolSpec(
                    "get_record",
                    "Read one record by id, such as EXEC-001.",
                    {
                        "type": "object",
                        "properties": {"id": {"type": "string"}},
                        "required": ["id"],
                    },
                ),
                get_record,
            ),
            QaTool(
                ToolSpec(
                    "list_records",
                    "List records of a kind by prefix, such as TC or EXEC.",
                    {
                        "type": "object",
                        "properties": {"prefix": {"type": "string"}},
                        "required": ["prefix"],
                    },
                ),
                list_records,
            ),
        ]
    )


def _factories(
    http: JsonHttp,
    ollama_url: str,
    opencode_url: str,
    model: str,
    tools: ToolRegistry,
):
    def own() -> tuple[Provider, OwnAgent]:
        provider = ollama.OllamaProvider(http, base_url=ollama_url, model=model)
        return provider, OwnAgent(provider, tools, model=model)

    def external() -> tuple[Provider, SingleShotAgent]:
        provider = opencode.OpenCodeProvider(http, base_url=opencode_url, model=model)
        return provider, SingleShotAgent(provider, model=model)

    return {"own": own, "opencode": external}


@ai_app.command("status")
def status_command(
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
) -> None:
    """Show which engines are reachable (nothing is sent to a model)."""
    http = default_http()
    providers: list[Provider] = [
        ollama.OllamaProvider(http, base_url=ollama_url),
        opencode.OpenCodeProvider(http, base_url=opencode_url),
    ]
    any_up = False
    for provider in providers:
        availability = provider.check_availability()
        any_up = any_up or availability.available
        mark = "available  " if availability.available else "unavailable"
        typer.echo(f"{provider.name:<9} {mark} {availability.detail}")
    if not any_up:
        raise typer.Exit(1)


def _print(answer: AgentAnswer) -> None:
    for statement in answer.statements:
        sources = f" [{', '.join(statement.sources)}]" if statement.sources else ""
        note = " (claimed to be a fact without a source)" if statement.demoted else ""
        typer.echo(f"{statement.kind.upper():<14} {statement.text}{sources}{note}")


@ai_app.command("ask")
def ask_command(
    question: Annotated[str, typer.Argument(help="What to ask.")],
    project: Annotated[str, typer.Option("--project", "-p", help="Project id.")],
    engine: Annotated[str, typer.Option(help="own, opencode, or auto.")] = "auto",
    model: Annotated[str, typer.Option(help="Model name for the engine.")] = "",
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
) -> None:
    """Ask a question. The engine can read the project's records (read-only)."""
    if engine not in MODES:
        _fail(f"engine must be one of {', '.join(MODES)}; got {engine!r}.")
    try:
        repository = open_repository(project, writable=False)
    except (ConfigurationError, ProjectError) as error:
        _fail(str(error))
    factories = _factories(
        default_http(), ollama_url, opencode_url, model, record_tools(repository)
    )
    try:
        choice = select_engine(engine, factories)
        typer.echo(f"Engine: {choice.mode} ({choice.detail})")
        answer = choice.engine.ask(question)
    except (NoProviderAvailable, ProviderError, StorageError) as error:
        _fail(str(error))
    _print(answer)
    typer.echo("AI output is analysis: it is not evidence, and nothing was changed.")
