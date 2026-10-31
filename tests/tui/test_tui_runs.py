import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import Button, Input

from qa_workbench.api import cli as api_cli
from qa_workbench.api.transport import PreparedRequest, TransportResponse
from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayResponse
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.sectest import authorization as auth
from qa_workbench.security.settings import SecuritySettings, save_settings
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.file_dialog import FileDialog
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for

DEFINITION = """
name: Users API
base_url: https://api.test
steps:
  - name: profile
    url: /me
    expect: {status: 200}
"""


class Transport:
    def __init__(self) -> None:
        self.requests: list[PreparedRequest] = []

    def send(self, request: PreparedRequest) -> TransportResponse:
        self.requests.append(request)
        body = json.dumps({"name": "ada"}).encode()
        return TransportResponse(
            200, {"Content-Type": "application/json"}, body, 5.0, ""
        )


class Gateway:
    """A GitLab with one commit and no merge requests."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, request):
        path = request.url.removeprefix("https://gitlab.test")
        self.urls.append(path)
        if path.endswith("/repository/commits"):
            body = [{"id": "a" * 40, "title": "Fix login", "author_name": "ada"}]
        elif path.endswith("/diff"):
            body = [{"new_path": "src/auth/login.py"}]
        elif "/repository/commits/" in path:
            body = {"id": "a" * 40, "title": "Fix login", "author_name": "ada"}
        elif path.endswith("/merge_requests"):
            body = []
        else:
            return GatewayResponse(404, {}, b"{}")
        return GatewayResponse(200, {}, json.dumps(body).encode())

    def post(self, request):  # pragma: no cover - reading never posts
        raise AssertionError("reading never posts")


@pytest.fixture(autouse=True)
def token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-fake-0123456789abcdef")


async def _until(pilot, condition, tries: int = 100) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _run(tmp_path: Path, page: str, hosts: tuple[str, ...], scenario) -> None:
    project = ProjectRepository(tmp_path).create(
        "Demo", repository="https://gitlab.test/nees/app"
    )
    repository = repository_for(tmp_path, project)
    if hosts:
        save_settings(repository.root, SecuritySettings(allowed_hosts=hosts))

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate(page)
            await pilot.pause()
            await scenario(app, pilot, repository)

    asyncio.run(runner())


def _notified(app, text: str) -> bool:
    return any(text in n.message for n in app._notifications)


def _fill(app, **values: str) -> None:
    for key, value in values.items():
        app.screen.query_one(f"#field-{key}", Input).value = value


def test_an_api_definition_is_chosen_from_the_tree_and_run(
    tmp_path, monkeypatch
) -> None:
    definition = tmp_path / "users.yaml"
    definition.write_text(DEFINITION)
    transport = Transport()
    monkeypatch.setattr(api_cli, "default_transport", lambda: transport)

    async def scenario(app, pilot, repository) -> None:
        await pilot.press("r")
        await _until(pilot, lambda: isinstance(app.screen, FileDialog))
        app.screen.choose(definition)
        await _until(pilot, lambda: repository.list_records("API").records)
        assert repository.get("API-001").metadata["status"] == "passed"
        await _until(pilot, lambda: _notified(app, "PASSED"))
        assert len(transport.requests) == 1

    _run(tmp_path, "api-testing", ("api.test",), scenario)


def test_an_api_run_to_a_host_that_is_not_allowed_sends_nothing(
    tmp_path, monkeypatch
) -> None:
    definition = tmp_path / "users.yaml"
    definition.write_text(DEFINITION)
    transport = Transport()
    monkeypatch.setattr(api_cli, "default_transport", lambda: transport)

    async def scenario(app, pilot, repository) -> None:
        await pilot.press("r")
        await _until(pilot, lambda: isinstance(app.screen, FileDialog))
        app.screen.choose(definition)
        await _until(pilot, lambda: _notified(app, "ERROR"))
        assert transport.requests == []
        assert repository.get("API-001").metadata["status"] != "passed"

    _run(tmp_path, "api-testing", (), scenario)


def test_security_checks_need_an_authorization_that_is_granted_and_revoked_here(
    tmp_path, monkeypatch
) -> None:
    async def scenario(app, pilot, repository) -> None:
        summary = lambda: str(  # noqa: E731
            app.query_one("#page-security").query_one("#browse-summary").render()
        )
        assert "No security-test authorization" in summary()

        await pilot.press("t")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, url="https://staging.example.com")
        app.screen.query_one("#submit", Button).press()
        await _until(pilot, lambda: _notified(app, "authoriz"))

        await pilot.press("u")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, by="Ana", purpose="release 1.4", host="staging.example.com")
        app.screen.query_one("#submit", Button).press()
        await _until(pilot, lambda: auth.load(repository.root) is not None)
        await _until(pilot, lambda: "valid, by Ana" in summary())

        await pilot.press("k")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, by="Ana")
        app.screen.query_one("#submit", Button).press()
        await _until(pilot, lambda: auth.load(repository.root) is None)

    _run(tmp_path, "security", (), scenario)


def test_a_release_analysis_is_started_from_the_page(tmp_path, monkeypatch) -> None:
    gateway = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: gateway)

    async def scenario(app, pilot, repository) -> None:
        await pilot.press("r")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        app.screen.query_one("#submit", Button).press()
        await _until(pilot, lambda: repository.list_records("REL").records)
        await _until(pilot, lambda: _notified(app, "risk"))

    _run(tmp_path, "release-analysis", ("gitlab.test",), scenario)


def test_a_release_analysis_on_a_host_that_is_not_allowed_reads_nothing(
    tmp_path, monkeypatch
) -> None:
    gateway = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: gateway)

    async def scenario(app, pilot, repository) -> None:
        await pilot.press("r")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        app.screen.query_one("#submit", Button).press()
        await _until(pilot, lambda: _notified(app, "outside"))
        assert not repository.list_records("REL").records

    _run(tmp_path, "release-analysis", (), scenario)
    assert gateway.urls == []
