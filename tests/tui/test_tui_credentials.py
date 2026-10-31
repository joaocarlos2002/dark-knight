import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Input, RadioButton, Static

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.credentials import CredentialStore
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.form import FormDialog

SECRET = "glpat-fake-0123456789abcdef"
URL = "https://gitlab.example.com/group/app"


@pytest.fixture(autouse=True)
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    for name in ("GITLAB_TOKEN", "NVIDIA_API_KEY", "OPENCODE_SERVER_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "config"


def _run(data_dir: Path, scenario, *, project=None, welcome: bool = False) -> None:
    async def runner() -> None:
        app = WorkbenchApp(
            project,
            preview_channel=PreviewChannel(data_dir / "preview"),
            data_dir=data_dir,
            welcome=welcome,
        )
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


async def _press(pilot, selector: str) -> None:
    pilot.app.screen.query_one(selector, Button).press()
    await pilot.pause()
    await pilot.pause()


async def _until(pilot, condition, tries: int = 50) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _fill(app, **values: str) -> None:
    for key, value in values.items():
        app.screen.query_one(f"#field-{key}", Input).value = value


def _form(app) -> str:
    return str(app.query_one("#settings-form", Static).render())


def test_settings_sets_shows_and_removes_a_token_without_showing_it(
    tmp_path, config
) -> None:
    project = ProjectRepository(tmp_path).create("Demo")
    store = CredentialStore(config)

    async def scenario(app, pilot) -> None:
        app.navigate("settings")
        await pilot.pause()
        app.query_one("#cat-credentials", RadioButton).value = True
        await pilot.pause()
        assert "GITLAB_TOKEN" in _form(app) and "not set" in _form(app)

        await pilot.press("ctrl+s")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        assert app.screen.query_one("#field-token", Input).password
        _fill(app, service="gitlab", token=SECRET)
        await _press(pilot, "#submit")
        await _until(pilot, lambda: store.get("gitlab") == SECRET)
        await _until(pilot, lambda: "set (stored)" in _form(app))
        assert SECRET not in _form(app)

        await pilot.press("ctrl+r")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, service="gitlab")
        await _press(pilot, "#submit")
        await _until(pilot, lambda: store.get("gitlab") is None)

    _run(tmp_path, scenario, project=project)


def test_a_bad_service_name_keeps_the_form_open_without_echoing_the_token(
    tmp_path,
) -> None:
    project = ProjectRepository(tmp_path).create("Demo")

    async def scenario(app, pilot) -> None:
        app.navigate("settings")
        await pilot.pause()
        app.query_one("#cat-credentials", RadioButton).value = True
        await pilot.pause()
        await pilot.press("ctrl+s")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, service="not a service!", token=SECRET)
        await _press(pilot, "#submit")

        assert isinstance(app.screen, FormDialog)
        error = str(app.screen.query_one("#form-error", Static).render())
        assert "not a service" in error and SECRET not in error

    _run(tmp_path, scenario, project=project)


def _create_project(app, pilot) -> None:
    async def go() -> None:
        await _press(pilot, "#confirm")
        _fill(app, name="Gotham", repository=URL)
        await _press(pilot, "#submit")
        await _until(pilot, lambda: isinstance(app.screen, ConfirmationDialog))

    return go()


def test_first_run_offers_to_keep_the_gitlab_token_after_the_host(
    tmp_path, config
) -> None:
    async def scenario(app, pilot) -> None:
        await _create_project(app, pilot)
        await _press(pilot, "#confirm")  # allow the host
        await _until(
            pilot,
            lambda: (
                "GitLab token"
                in str(app.screen.query_one("#dialog-title", Static).render())
                if isinstance(app.screen, ConfirmationDialog)
                else False
            ),
        )
        await _press(pilot, "#confirm")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        assert app.screen.query_one("#field-token", Input).password
        _fill(app, token=SECRET)
        await _press(pilot, "#submit")

        await _until(pilot, lambda: CredentialStore(config).get("gitlab") == SECRET)

    _run(tmp_path, scenario, welcome=True)


def test_declining_the_token_stores_nothing(tmp_path, config) -> None:
    async def scenario(app, pilot) -> None:
        await _create_project(app, pilot)
        await _press(pilot, "#cancel")  # do not allow the host
        await _until(
            pilot,
            lambda: (
                isinstance(app.screen, ConfirmationDialog)
                and "token"
                in str(app.screen.query_one("#dialog-title", Static).render())
            ),
        )
        await _press(pilot, "#cancel")

        assert not isinstance(app.screen, (ConfirmationDialog, FormDialog))
        assert CredentialStore(config).names() == []

    _run(tmp_path, scenario, welcome=True)


def test_no_token_offer_when_one_is_already_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", SECRET)

    async def scenario(app, pilot) -> None:
        await _create_project(app, pilot)
        await _press(pilot, "#confirm")  # allow the host
        await pilot.pause()
        await pilot.pause()

        assert not isinstance(app.screen, (ConfirmationDialog, FormDialog))

    _run(tmp_path, scenario, welcome=True)
