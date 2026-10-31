import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import Button, Input

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayResponse
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.settings import SecuritySettings, save_settings
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for

ISSUE = {
    "iid": 12,
    "title": "Botão quebrado",
    "state": "opened",
    "labels": ["team::dev", "workflow::QA"],
    "web_url": "https://gitlab.test/nees/frontend/-/issues/12",
    "references": {"full": "nees/frontend#12"},
    "assignees": [{"username": "ada"}],
}


class Gateway:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.params: list[dict] = []

    def get(self, request):
        path = request.url.removeprefix("https://gitlab.test")
        self.urls.append(path)
        self.params.append(dict(request.params))
        if path == "/api/v4/groups/nees/issues":
            body = [ISSUE]
        elif path == "/api/v4/projects/nees%2Ffrontend/issues/12/links":
            body = [
                {
                    "iid": 3,
                    "title": "Irmã",
                    "state": "opened",
                    "references": {"full": "nees/backend#3"},
                }
            ]
        elif path.startswith("/api/v4/projects/nees%2Ffrontend/issues/12/"):
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


def _text(app, selector: str) -> str:
    return str(app.query_one("#page-board").query_one(selector).render())


def _run(tmp_path: Path, monkeypatch, allowed: bool, scenario) -> Gateway:
    project = ProjectRepository(tmp_path).create(
        "Demo", repository="https://gitlab.test/nees/app"
    )
    if allowed:
        root = repository_for(tmp_path, project).root
        save_settings(root, SecuritySettings(allowed_hosts=("gitlab.test",)))
    gateway = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: gateway)

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate("board")
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())
    return gateway


async def _read(app, pilot) -> None:
    await pilot.press("r")
    await _until(pilot, lambda: isinstance(app.screen, FormDialog))
    app.screen.query_one("#field-labels", Input).value = "team::dev,workflow::QA"
    app.screen.query_one("#submit", Button).press()


def test_a_column_is_read_and_an_issue_shows_its_links(tmp_path, monkeypatch) -> None:
    async def scenario(app, pilot) -> None:
        await _read(app, pilot)
        await _until(pilot, lambda: "1 issue(s)" in _text(app, "#board-summary"))
        await _until(pilot, lambda: "Botão quebrado" in _text(app, "#board-detail"))
        await pilot.press("l")
        await _until(pilot, lambda: "nees/backend#3" in _text(app, "#board-detail"))

    gateway = _run(tmp_path, monkeypatch, True, scenario)
    first = next(p for p in gateway.params if "labels" in p)
    assert first["labels"] == "team::dev,workflow::QA"
    assert first["not[labels]"] == "type::testcase"


def test_a_host_that_is_not_allowed_reads_nothing(tmp_path, monkeypatch) -> None:
    async def scenario(app, pilot) -> None:
        await _read(app, pilot)
        await _until(
            pilot,
            lambda: "outside the authorized hosts" in _text(app, "#board-summary"),
        )

    gateway = _run(tmp_path, monkeypatch, False, scenario)
    assert gateway.urls == []
