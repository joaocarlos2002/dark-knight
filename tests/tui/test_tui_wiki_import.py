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

SLUG = "Requisitos/GE01.01-Autorizar"
PAGES = [
    {
        "slug": SLUG,
        "title": "GE01.01 Autorizar",
        "format": "markdown",
        "content": "O gestor autoriza. RN-GE01.01.01 vale.",
    }
]


class Gateway:
    """A tiny GitLab: serves the group wiki list, nothing else."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, request):
        self.urls.append(request.url)
        if request.url.endswith("/groups/nees/wikis"):
            return GatewayResponse(200, {}, json.dumps(PAGES).encode())
        return GatewayResponse(404, {}, b"{}")

    def post(self, request):  # pragma: no cover - the wiki is read only
        raise AssertionError("reading the wiki never posts")


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


def _run(tmp_path: Path, allowed: bool, monkeypatch, scenario) -> Gateway:
    project = ProjectRepository(tmp_path).create(
        "Demo", repository="https://gitlab.test/nees/app"
    )
    root = repository_for(tmp_path, project).root
    if allowed:
        save_settings(root, SecuritySettings(allowed_hosts=("gitlab.test",)))
    gateway = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: gateway)

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate("requirements")
            await pilot.pause()
            await scenario(app, pilot, repository_for(tmp_path, project))

    asyncio.run(runner())
    return gateway


async def _submit(app, pilot) -> None:
    await pilot.press("w")
    await _until(pilot, lambda: isinstance(app.screen, FormDialog))
    app.screen.query_one("#field-prefix", Input).value = "Requisitos/"
    app.screen.query_one("#field-group", Input).value = "nees"
    app.screen.query_one("#submit", Button).press()


def test_w_imports_the_wiki_pages_as_draft_requirements(tmp_path, monkeypatch) -> None:
    async def scenario(app, pilot, repository) -> None:
        await _submit(app, pilot)
        await _until(pilot, lambda: repository.list_records("REQ").records)
        record = repository.list_records("REQ").records[0]
        assert record.metadata["status"] == "draft"
        assert record.metadata["source_ref"] == SLUG
        assert record.metadata["business_rules"] == ["RN-GE01.01.01"]

    gateway = _run(tmp_path, True, monkeypatch, scenario)
    assert gateway.urls and all("/api/v4/groups/nees/wikis" in u for u in gateway.urls)


def test_a_host_that_is_not_allowed_imports_nothing(tmp_path, monkeypatch) -> None:
    async def scenario(app, pilot, repository) -> None:
        await _submit(app, pilot)
        await _until(
            pilot,
            lambda: any("outside" in n.message for n in app._notifications),
        )
        assert not repository.list_records("REQ").records

    gateway = _run(tmp_path, False, monkeypatch, scenario)
    assert gateway.urls == []
