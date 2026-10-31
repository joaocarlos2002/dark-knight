"""``batman ai`` commands: check the engines and ask a question about a project."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.ai import nvidia, ollama, opencode
from qa_workbench.ai.agent import (
    AgentAnswer,
    OwnAgent,
    QaTool,
    SingleShotAgent,
    ToolRegistry,
)
from qa_workbench.ai.contract import Provider, ToolSpec
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.guarded import guarded_http
from qa_workbench.ai.http import HttpxJson, JsonHttp
from qa_workbench.ai.selection import MODES, REMOTE, select_engine
from qa_workbench.core.config import ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.security.audit import AuditError
from qa_workbench.security.settings import SecuritySettingsError
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
NvidiaUrl = Annotated[
    str, typer.Option("--nvidia-url", envvar="NVIDIA_BASE_URL", help="NVIDIA API.")
]
ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id (its security settings).")
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
    nvidia_url: str,
    model: str,
    tools: ToolRegistry,
):
    def own() -> tuple[Provider, OwnAgent]:
        provider = ollama.OllamaProvider(http, base_url=ollama_url, model=model)
        return provider, OwnAgent(provider, tools, model=model)

    def external() -> tuple[Provider, SingleShotAgent]:
        provider = opencode.OpenCodeProvider(http, base_url=opencode_url, model=model)
        return provider, SingleShotAgent(provider, model=model)

    def hosted() -> tuple[Provider, SingleShotAgent]:
        provider = nvidia.NvidiaProvider(http, base_url=nvidia_url, model=model)
        return provider, SingleShotAgent(provider, model=model)

    return {"own": own, "opencode": external, "nvidia": hosted}


def _guarded(
    project: str, writable: bool = False
) -> tuple[JsonHttp, MarkdownRepository]:
    """The HTTP client behind the project's action guard, and its repository."""
    try:
        repository = open_repository(project, writable=writable)
        return guarded_http(default_http(), repository.root), repository
    except (
        ConfigurationError,
        ProjectError,
        AuditError,
        SecuritySettingsError,
    ) as error:
        _fail(str(error))


@ai_app.command("status")
def status_command(
    project: Annotated[
        str, typer.Option("--project", "-p", help="Also check the remote NVIDIA API.")
    ] = "",
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
    nvidia_url: NvidiaUrl = nvidia.DEFAULT_URL,
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
    hosted = nvidia.NvidiaProvider(http, base_url=nvidia_url)
    key = "present" if hosted.key_present() else "missing"
    if not project:
        # A remote engine is only contacted through a project's action guard.
        typer.echo(
            f"{hosted.name:<9} not checked  remote engine; API key {key}. "
            "Pass --project to check it."
        )
    else:
        guarded, _ = _guarded(project)
        hosted = nvidia.NvidiaProvider(guarded, base_url=nvidia_url)
        availability = hosted.check_availability()
        any_up = any_up or availability.available
        mark = "available  " if availability.available else "unavailable"
        typer.echo(f"{hosted.name:<9} {mark} {availability.detail}; API key {key}")
    if not any_up:
        raise typer.Exit(1)


@ai_app.command("models")
def models_command(
    project: ProjectOption,
    engine: Annotated[str, typer.Option(help="own, opencode, or nvidia.")] = "nvidia",
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
    nvidia_url: NvidiaUrl = nvidia.DEFAULT_URL,
) -> None:
    """List the models an engine offers (pass one with `ask --model`)."""
    if engine not in ("own", "opencode", "nvidia"):
        _fail(f"engine must be own, opencode, or nvidia; got {engine!r}.")
    http, repository = _guarded(project)
    factories = _factories(
        http, ollama_url, opencode_url, nvidia_url, "", record_tools(repository)
    )
    try:
        provider, _ = factories[engine]()
        models = provider.list_models()
    except ProviderError as error:
        _fail(str(error))
    if engine in REMOTE:
        typer.echo(f"Remote engine: {nvidia.host_of(nvidia_url)}")
    for model in models:
        typer.echo(model)


def _print(answer: AgentAnswer) -> None:
    for statement in answer.statements:
        sources = f" [{', '.join(statement.sources)}]" if statement.sources else ""
        note = " (claimed to be a fact without a source)" if statement.demoted else ""
        typer.echo(f"{statement.kind.upper():<14} {statement.text}{sources}{note}")


@ai_app.command("ask")
def ask_command(
    question: Annotated[str, typer.Argument(help="What to ask.")],
    project: Annotated[str, typer.Option("--project", "-p", help="Project id.")],
    engine: Annotated[
        str, typer.Option(help="own, opencode, nvidia (remote), or auto.")
    ] = "auto",
    model: Annotated[str, typer.Option(help="Model name for the engine.")] = "",
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
    nvidia_url: NvidiaUrl = nvidia.DEFAULT_URL,
) -> None:
    """Ask a question. The engine can read the project's records (read-only)."""
    if engine not in MODES:
        _fail(f"engine must be one of {', '.join(MODES)}; got {engine!r}.")
    http, repository = _guarded(project)
    factories = _factories(
        http, ollama_url, opencode_url, nvidia_url, model, record_tools(repository)
    )
    try:
        choice = select_engine(engine, factories)
        typer.echo(f"Engine: {choice.mode} ({choice.detail})")
        if choice.mode in REMOTE:
            typer.echo(
                "Remote engine: the question and project context leave this machine "
                "(secrets are redacted first)."
            )
        answer = choice.engine.ask(question)
    except (NoProviderAvailable, ProviderError, StorageError) as error:
        _fail(str(error))
    _print(answer)
    typer.echo("AI output is analysis: it is not evidence, and nothing was changed.")
