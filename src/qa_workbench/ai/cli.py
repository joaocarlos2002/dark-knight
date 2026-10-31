"""``batman ai`` commands: check the engines and ask a question about a project."""

from typing import Annotated, NoReturn

import typer

from qa_workbench.ai import claude_code, nvidia, ollama, opencode
from qa_workbench.ai.agent import (
    AgentAnswer,
    OwnAgent,
    QaTool,
    SingleShotAgent,
    ToolRegistry,
)
from qa_workbench.ai.contract import Provider, ToolSpec
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.guarded import guarded_http, guarded_runner
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
ClaudePath = Annotated[
    str,
    typer.Option(
        "--claude-path",
        envvar=claude_code.PATH_VARIABLE,
        help="The claude executable (found automatically when installed).",
    ),
]
ProjectOption = Annotated[
    str, typer.Option("--project", "-p", help="Project id (its security settings).")
]


def default_http() -> JsonHttp:
    """The real HTTP client. Tests replace this so nothing touches the network."""
    return HttpxJson()


def default_runner() -> claude_code.Runner:
    """The real process runner. Tests replace this so nothing is started."""
    return claude_code.SubprocessRunner()


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
    runner: claude_code.Runner | None = None,
    claude_path: str = "",
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

    def claude() -> tuple[Provider, SingleShotAgent]:
        provider = claude_code.ClaudeCodeProvider(
            runner or default_runner(), model=model, executable=claude_path or None
        )
        return provider, SingleShotAgent(provider, model=model)

    return {"own": own, "opencode": external, "nvidia": hosted, "claude": claude}


def _guarded_runner(repository: MarkdownRepository) -> claude_code.Runner:
    try:
        return guarded_runner(default_runner(), repository.root, claude_code.HOST_URL)
    except (AuditError, SecuritySettingsError) as error:
        _fail(str(error))


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
    claude_path: ClaudePath = "",
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
    claude = claude_code.ClaudeCodeProvider(
        default_runner(), executable=claude_path or None
    ).check_availability()
    any_up = any_up or claude.available
    mark = "available  " if claude.available else "unavailable"
    typer.echo(f"{claude_code.NAME:<9} {mark} {claude.detail}")
    if not any_up:
        raise typer.Exit(1)


@ai_app.command("models")
def models_command(
    project: ProjectOption,
    engine: Annotated[
        str, typer.Option(help="own, opencode, nvidia, or claude.")
    ] = "nvidia",
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
    nvidia_url: NvidiaUrl = nvidia.DEFAULT_URL,
    claude_path: ClaudePath = "",
) -> None:
    """List the models an engine offers (pass one with `ask --model`)."""
    if engine not in ("own", "opencode", "nvidia", "claude"):
        _fail(f"engine must be own, opencode, nvidia, or claude; got {engine!r}.")
    http, repository = _guarded(project)
    factories = _factories(
        http,
        ollama_url,
        opencode_url,
        nvidia_url,
        "",
        record_tools(repository),
        claude_path=claude_path,
    )
    try:
        provider, _ = factories[engine]()
        models = provider.list_models()
    except ProviderError as error:
        _fail(str(error))
    if engine in REMOTE:
        host = nvidia.host_of(
            nvidia_url if engine == "nvidia" else claude_code.HOST_URL
        )
        typer.echo(f"Remote engine: {host}")
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
        str, typer.Option(help="own, opencode, nvidia or claude (remote), or auto.")
    ] = "auto",
    model: Annotated[str, typer.Option(help="Model name for the engine.")] = "",
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
    nvidia_url: NvidiaUrl = nvidia.DEFAULT_URL,
    claude_path: ClaudePath = "",
) -> None:
    """Ask a question. The engine can read the project's records (read-only)."""
    if engine not in MODES:
        _fail(f"engine must be one of {', '.join(MODES)}; got {engine!r}.")
    http, repository = _guarded(project)
    factories = _factories(
        http,
        ollama_url,
        opencode_url,
        nvidia_url,
        model,
        record_tools(repository),
        _guarded_runner(repository),
        claude_path,
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


@ai_app.command("populate")
def populate_command(
    project: ProjectOption,
    by: Annotated[str, typer.Option("--by", help="Who is responsible for this run.")],
    engine: Annotated[
        str, typer.Option(help="own, opencode, nvidia or claude (remote), or auto.")
    ] = "",
    model: Annotated[str, typer.Option(help="Model name for the engine.")] = "",
    limit: Annotated[
        int, typer.Option(min=1, max=50, help="Requirements to ask about.")
    ] = 5,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Only say what would be asked.")
    ] = False,
    remote_ok: Annotated[
        bool,
        typer.Option(
            "--remote-ok",
            help="Allow a remote engine: the requirement text leaves this machine.",
        ),
    ] = False,
    wiki: Annotated[
        bool, typer.Option("--wiki", help="Import the group wiki's requirements first.")
    ] = False,
    ollama_url: OllamaUrl = ollama.DEFAULT_URL,
    opencode_url: OpenCodeUrl = opencode.DEFAULT_URL,
    nvidia_url: NvidiaUrl = nvidia.DEFAULT_URL,
    claude_path: ClaudePath = "",
) -> None:
    """Ask the AI for draft test cases for the requirements that have none. Every
    case is a draft that waits for review (`batman review`); nothing is final."""
    from qa_workbench.ai import populate as populate_ai
    from qa_workbench.ai.alfred import (
        AlfredSettings,
        AlfredSettingsError,
        choose_provider,
        load_settings,
    )

    _http, repository = _guarded(project, writable=True)
    chosen = engine or ""
    if chosen and chosen not in MODES:
        _fail(f"engine must be one of {', '.join(MODES)}; got {chosen!r}.")
    try:
        saved = load_settings(repository.root)
    except AlfredSettingsError:
        saved = AlfredSettings()
    settings = AlfredSettings(
        engine=chosen or saved.engine,
        model=model or saved.model,
        style=saved.style,
        language=saved.language,
        ollama_url=ollama_url,
        opencode_url=opencode_url,
        nvidia_url=nvidia_url,
    )
    if wiki:
        _import_wiki_first(project, repository)
    targets = populate_ai.pending_requirements(repository, limit)
    if not targets:
        typer.echo("Every requirement already has a test case. Nothing to ask.")
        return
    if dry_run:
        typer.echo(f"Would ask about {len(targets)} requirement(s):")
        for record in targets:
            typer.echo(f"  {record.id}  {record.metadata['title']}")
        return
    try:
        choice = choose_provider(settings, repository, default_http(), default_runner())
        typer.echo(f"Engine: {choice.mode} ({choice.detail})")
        if choice.mode in REMOTE and not remote_ok:
            _fail(
                f"{choice.mode} is a remote engine: the requirement text would leave "
                "this machine. Run again with --remote-ok to allow it."
            )
        report = populate_ai.populate(
            repository,
            choice.provider,
            model=settings.model,
            limit=limit,
            actor=by,
            language=settings.language,
            progress=typer.echo,
        )
    except (NoProviderAvailable, ProviderError, StorageError) as error:
        _fail(str(error))
    typer.echo(
        f"{len(report.created)} draft case(s) created"
        + (f" in {report.suite}" if report.suite else "")
        + f", {len(report.failed)} requirement(s) not used."
    )
    typer.echo("They are drafts: review them with `batman review pending`.")
    if report.failed:
        raise typer.Exit(1)


def _import_wiki_first(project: str, repository: MarkdownRepository) -> None:
    from qa_workbench.integrations.errors import IntegrationError
    from qa_workbench.integrations.gitlab.cli import wiki_for
    from qa_workbench.requirements.wiki_import import import_wiki_pages

    wiki, group, base_url = wiki_for(project, None, "GITLAB_TOKEN", None)
    try:
        pages = wiki.list_pages(with_content=True)
        report = import_wiki_pages(repository, pages, base_url=base_url, group=group)
    except (IntegrationError, StorageError) as error:
        _fail(str(error))
    typer.echo(
        f"Wiki: {len(report.created)} created, {len(report.updated)} updated, "
        f"{len(report.skipped)} unchanged."
    )
