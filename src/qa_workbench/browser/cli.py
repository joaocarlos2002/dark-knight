"""``batman browser`` and ``batman doctor`` commands."""

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from qa_workbench.browser.agent import BrowserAgent, register_artifacts
from qa_workbench.browser.chromium import BrowserSetup
from qa_workbench.browser.errors import AssertionFailed, BrowserError, BrowserSetupError
from qa_workbench.browser.playwright_driver import PlaywrightDriver
from qa_workbench.browser.ports import BrowserDriver, BrowserMode
from qa_workbench.browser.preview import PreviewChannel, PreviewController
from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.projects.errors import ProjectError
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.credentials import (
    CredentialError,
    default_store,
    token_report,
)
from qa_workbench.security.guard import ActionGuard, SecurityError
from qa_workbench.security.settings import SecuritySettingsError, load_settings
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.workspace import open_repository

browser_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Drive a web browser with Playwright and follow it in the workbench.",
)

PREVIEW_DIRECTORY = "browser-preview"


def preview_channel(config: AppConfig) -> PreviewChannel:
    """Where the running browser publishes what the TUI shows."""
    return PreviewChannel(config.data_dir / PREVIEW_DIRECTORY)


def default_driver() -> BrowserDriver:
    """The real driver. Tests replace this to avoid launching a browser."""
    return PlaywrightDriver()


def default_setup() -> BrowserSetup:
    """The real setup. Tests replace this to avoid downloading anything."""
    return BrowserSetup()


def _fail(message: str) -> NoReturn:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(1)


def _confirm_install(assume_yes: bool):
    def confirm(question: str) -> bool:
        if assume_yes:
            return True
        if not sys.stdin.isatty():
            return False
        try:
            return typer.confirm(question)
        except typer.Abort:
            return False  # no answer (closed input) counts as "not now"

    return confirm


def report_setup(setup: BrowserSetup, *, fix: bool, assume_yes: bool) -> bool:
    """Print the browser status; with ``fix``, offer to install what is missing."""
    status = setup.status()
    if status.ready:
        typer.echo(f"Browser: ready (Chromium at {status.chromium_path})")
        return True
    typer.echo(f"Browser: NOT ready. {status.detail}")
    if not fix:
        typer.echo("Run `batman doctor --fix` to install it.")
        return False
    try:
        installed = setup.ensure(_confirm_install(assume_yes))
    except BrowserSetupError as error:
        typer.echo(f"Error: {error}", err=True)
        return False
    typer.echo(f"Browser: installed (Chromium at {installed.chromium_path})")
    return True


@browser_app.command("doctor")
def doctor_command(
    fix: Annotated[
        bool, typer.Option("--fix", help="Install what is missing.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask first.")] = False,
) -> None:
    """Check what the workbench needs: the web-test browser and the AI engines."""
    ready = report_setup(default_setup(), fix=fix, assume_yes=yes)
    # Nothing is sent anywhere here, and no value is ever shown.
    # `batman ai status --project ID` checks that the AI engines are reachable.
    try:
        report = token_report(default_store())
    except CredentialError as error:
        typer.echo(f"API tokens: {error}")
    else:
        typer.echo("API tokens (`batman config token set NAME` to add one):")
        for variable, source in report:
            state = f"set ({source})" if source else "not set"
            typer.echo(f"  {variable:<24} {state}")
    if not ready:
        raise typer.Exit(1)


@browser_app.command("install")
def install_command(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask first.")] = False,
) -> None:
    """Download the browser used for web tests."""
    if not report_setup(default_setup(), fix=True, assume_yes=yes):
        raise typer.Exit(1)


@browser_app.command("status")
def status_command() -> None:
    """Show what the running browser last reported."""
    try:
        config = AppConfig.load()
        state = preview_channel(config).read()
    except (ConfigurationError, BrowserError) as error:
        _fail(str(error))
    if state is None:
        typer.echo("No browser has published a preview yet.")
        return
    for name, value in vars(state).items():
        typer.echo(f"{name}: {value}")


@browser_app.command("control")
def control_command(
    mode: Annotated[
        str | None, typer.Option(help="headless, preview, or visible.")
    ] = None,
    pause: Annotated[bool, typer.Option("--pause", help="Pause the run.")] = False,
    resume: Annotated[bool, typer.Option("--resume", help="Resume the run.")] = False,
) -> None:
    """Ask the running browser to change mode or pause (applies between actions)."""
    if pause and resume:
        _fail("Choose either --pause or --resume, not both.")
    if mode is not None and mode not in {m.value for m in BrowserMode}:
        _fail(f"Unknown mode {mode!r}. Use headless, preview, or visible.")
    if mode is None and not pause and not resume:
        _fail("Nothing to do: pass --mode, --pause, or --resume.")
    try:
        channel = preview_channel(AppConfig.load())
        channel.request(mode=mode, paused=True if pause else False if resume else None)
    except (ConfigurationError, BrowserError, OSError) as error:
        _fail(str(error))
    typer.echo("Request sent. It applies between browser actions.")


@browser_app.command("run")
def run_command(
    url: Annotated[str, typer.Argument(help="Page to open.")],
    mode: Annotated[
        str, typer.Option(help="headless, preview (default), or visible.")
    ] = "preview",
    out: Annotated[
        Path | None, typer.Option("--out", help="Folder for screenshots, trace, video.")
    ] = None,
    expect_text: Annotated[
        str | None, typer.Option("--expect-text", help="Text the page must contain.")
    ] = None,
    project: Annotated[
        str | None,
        typer.Option("--project", "-p", help="Register the files as evidence."),
    ] = None,
    execution: Annotated[
        str | None,
        typer.Option("--execution", help="Execution to link, e.g. EXEC-001."),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Install the browser without asking.")
    ] = False,
) -> None:
    """Open a page, capture a screenshot, and report what the browser saw."""
    if mode not in {m.value for m in BrowserMode}:
        _fail(f"Unknown mode {mode!r}. Use headless, preview, or visible.")
    if execution and not project:
        _fail("--execution needs --project.")
    try:
        config = AppConfig.load()
        repository = open_repository(project, writable=True) if project else None
        store = EvidenceStore(repository) if repository else None
        guard = (
            ActionGuard(load_settings(repository.root), AuditLog(repository.root))
            if repository
            else None
        )
    except (
        ConfigurationError,
        ProjectError,
        StorageError,
        SecuritySettingsError,
    ) as error:
        _fail(str(error))
    try:
        default_setup().ensure(_confirm_install(yes))
    except BrowserSetupError as error:
        _fail(str(error))
    artifacts_dir = out or Path(config.data_dir) / "browser-runs" / _run_name()
    agent = BrowserAgent(
        driver=default_driver(),
        artifacts_dir=artifacts_dir,
        controller=PreviewController(BrowserMode(mode)),
        channel=preview_channel(config),
        guard=guard,
    )
    outcome = _drive(agent, url, expect_text)
    try:
        artifacts = agent.close()
    except BrowserError as error:
        _fail(f"The browser did not close cleanly: {error}")
    typer.echo(f"Console errors: {len(agent.observations.console_errors)}")
    typer.echo(f"HTTP failures: {len(agent.observations.http_failures)}")
    for failure in agent.screenshot_failures:
        typer.echo(f"Screenshot problem (not a test failure): {failure}")
    if store is not None:
        try:
            records = register_artifacts(
                store, artifacts, execution=execution, source_url=_source_url(url)
            )
        except (StorageError, ValueError) as error:
            _fail(f"Evidence could not be registered: {error}")
        for record in records:
            typer.echo(f"Registered {record.id}")
    else:
        for path, kind in artifacts.files():
            typer.echo(f"Saved {kind}: {path}")
    if outcome:
        _fail(outcome)


def _drive(agent: BrowserAgent, url: str, expect_text: str | None) -> str:
    """Run the page visit; returns an error message, or an empty string."""
    try:
        agent.start()
    except (BrowserError, BrowserSetupError) as error:
        _fail(str(error))
    problem = ""
    try:
        agent.navigate(url)
        if expect_text is not None:
            agent.expect_text("body", expect_text)
        agent.screenshot("page")
    except SecurityError as error:
        problem = f"Not authorized: {error}"
    except AssertionFailed as error:
        problem = f"Check failed: {error}"
    except BrowserError as error:
        problem = f"Browser error: {error}"
    return problem


def _source_url(url: str) -> str | None:
    """Evidence records only accept web URLs as a source (not file:// pages)."""
    return url if url.startswith(("http://", "https://")) else None


def _run_name() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
