import asyncio
import base64
import json
from pathlib import Path

import pytest

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayResponse
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.settings import SecuritySettings, save_settings
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.workspace import repository_for

PREFIX = "/api/v4/projects/nees%2Fapp"


class Gateway:
    """A tiny GitLab repository: a root with one folder and one file."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, request):
        path = request.url.removeprefix("https://gitlab.test")
        self.urls.append(path)
        if path == PREFIX:
            body = {"default_branch": "main"}
        elif path == PREFIX + "/repository/tree":
            if request.params.get("path") == "src":
                body = [{"name": "Login.tsx", "type": "blob", "path": "src/Login.tsx"}]
            else:
                body = [
                    {"name": "src", "type": "tree", "path": "src"},
                    {"name": "README.md", "type": "blob", "path": "README.md"},
                ]
        elif path.endswith("/repository/files/src%2FLogin.tsx"):
            text = b"login(); // password=hunter22\n"
            body = {"size": len(text), "content": base64.b64encode(text).decode()}
        else:
            return GatewayResponse(404, {}, b"{}")
        return GatewayResponse(200, {}, json.dumps(body).encode())

    def post(self, request):  # pragma: no cover - the repository is read only
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
            app.navigate("repository")
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())
    return gateway


def _text(app, selector: str) -> str:
    return str(app.query_one(selector).render())


def test_the_repository_is_browsed_into_a_folder_and_a_file_is_read_masked(
    tmp_path, monkeypatch
) -> None:
    async def scenario(app, pilot) -> None:
        assert "Nothing is fetched" in _text(app, "#repo-summary")
        await pilot.press("r")
        await _until(pilot, lambda: "2 entries" in _text(app, "#repo-summary"))
        await pilot.press("o")  # the folder is first
        await _until(pilot, lambda: "1 entries" in _text(app, "#repo-summary"))
        await pilot.press("o")
        await _until(pilot, lambda: "login();" in _text(app, "#repo-detail"))
        shown = _text(app, "#repo-detail")
        assert "hunter22" not in shown and "Untrusted" in shown

    _run(tmp_path, monkeypatch, True, scenario)


def test_a_host_that_is_not_allowed_reads_nothing(tmp_path, monkeypatch) -> None:
    async def scenario(app, pilot) -> None:
        await pilot.press("r")
        await pilot.pause()
        assert "outside the authorized hosts" in _text(app, "#repo-summary")

    gateway = _run(tmp_path, monkeypatch, False, scenario)
    assert gateway.urls == []
