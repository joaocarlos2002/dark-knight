import asyncio
from pathlib import Path

from textual.widgets import Button, Input, Static

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.settings import load_settings
from qa_workbench.tui import onboarding
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for

URL = "https://gitlab.example.com/group/app"


def _run(data_dir: Path, scenario, *, welcome: bool = True) -> None:
    async def runner() -> None:
        app = WorkbenchApp(
            None,
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


def test_a_new_workbench_welcomes_and_offers_to_create_a_project(tmp_path) -> None:
    async def scenario(app, pilot) -> None:
        assert isinstance(app.screen, ConfirmationDialog)
        text = str(app.screen.query_one("#dialog-title", Static).render())
        assert "WAYNE INDUSTRIES" in text and "DARK KNIGHT QA" in text

    _run(tmp_path, scenario)


def test_the_welcome_creates_the_project_opens_it_and_asks_before_allowing_the_host(
    tmp_path,
) -> None:
    async def scenario(app, pilot) -> None:
        await _press(pilot, "#confirm")
        assert isinstance(app.screen, FormDialog)
        _fill(app, name="Gotham Checkout", repository=URL)
        await _press(pilot, "#submit")

        await _until(pilot, lambda: app.project is not None)
        assert app.project.name == "Gotham Checkout"
        assert app.project.repository == URL
        # The host is a security decision: asked, not assumed.
        await _until(pilot, lambda: isinstance(app.screen, ConfirmationDialog))
        project = app.project
        root = repository_for(tmp_path, project).root
        assert load_settings(root).allowed_hosts == ()

        await _press(pilot, "#confirm")
        await _until(pilot, lambda: load_settings(root).allowed_hosts)
        assert load_settings(root).allowed_hosts == ("gitlab.example.com",)
        kinds = [entry.kind for entry in AuditLog(root).entries()]
        assert "settings_changed" in kinds

    _run(tmp_path, scenario)


def test_declining_the_host_leaves_it_blocked(tmp_path) -> None:
    async def scenario(app, pilot) -> None:
        await _press(pilot, "#confirm")
        _fill(app, name="Gotham Checkout", repository=URL)
        await _press(pilot, "#submit")
        await _until(pilot, lambda: isinstance(app.screen, ConfirmationDialog))

        await _press(pilot, "#cancel")

        root = repository_for(tmp_path, app.project).root
        assert load_settings(root).allowed_hosts == ()

    _run(tmp_path, scenario)


def test_a_project_without_a_repository_asks_nothing_about_hosts(tmp_path) -> None:
    async def scenario(app, pilot) -> None:
        await _press(pilot, "#confirm")
        _fill(app, name="Local only")
        await _press(pilot, "#submit")

        await _until(pilot, lambda: app.project is not None)
        await pilot.pause()
        assert not isinstance(app.screen, ConfirmationDialog)

    _run(tmp_path, scenario)


def test_a_bad_repository_url_keeps_the_form_open_with_what_was_typed(
    tmp_path,
) -> None:
    async def scenario(app, pilot) -> None:
        await _press(pilot, "#confirm")
        _fill(app, name="Gotham", repository="not a url")
        await _press(pilot, "#submit")

        assert isinstance(app.screen, FormDialog)
        assert "https://" in str(app.screen.query_one("#form-error", Static).render())
        assert app.screen.query_one("#field-name", Input).value == "Gotham"
        assert ProjectRepository(tmp_path).list_projects().projects == ()

    _run(tmp_path, scenario)


def test_later_leaves_the_workbench_empty_and_nothing_is_created(tmp_path) -> None:
    async def scenario(app, pilot) -> None:
        await _press(pilot, "#cancel")

        assert app.project is None
        assert not isinstance(app.screen, ConfirmationDialog)
        assert ProjectRepository(tmp_path).list_projects().projects == ()

    _run(tmp_path, scenario)


def test_no_welcome_when_a_project_already_exists(tmp_path) -> None:
    ProjectRepository(tmp_path).create("Existing")

    async def scenario(app, pilot) -> None:
        assert not isinstance(app.screen, ConfirmationDialog)

    _run(tmp_path, scenario)


def test_no_welcome_unless_asked_for(tmp_path) -> None:
    async def scenario(app, pilot) -> None:
        assert not isinstance(app.screen, ConfirmationDialog)

    _run(tmp_path, scenario, welcome=False)


def test_which_hosts_are_worth_allowing() -> None:
    assert onboarding.repository_host(URL) == "gitlab.example.com"
    assert onboarding.repository_host("http://127.0.0.1:8080/g/app") == ""
    assert onboarding.repository_host("git@gitlab.example.com:g/app.git") == ""
    assert onboarding.validate_repository({"repository": ""}) is None
    assert onboarding.validate_repository({"repository": URL}) is None
    assert onboarding.validate_repository({"repository": "ftp://x.test/a"})
