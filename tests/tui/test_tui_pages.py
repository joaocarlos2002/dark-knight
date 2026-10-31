import asyncio
from pathlib import Path

import pytest
from test_tui_data import _case, _execution
from textual.widgets import Button, Input, Static
from textual.widgets import DataTable as TextualDataTable

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.pages.projects import validate_new_project
from qa_workbench.workspace import repository_for


def _run(data_dir: Path, scenario, project=None, size=(140, 50)) -> None:
    async def runner() -> None:
        app = WorkbenchApp(
            project,
            preview_channel=PreviewChannel(data_dir / "preview"),
            data_dir=data_dir,
        )
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


async def _click(pilot, selector: str) -> None:
    """Press a button of the open dialog, then let its async handler run.

    The button is pressed directly rather than by pointer position: the layout
    moves when an error line appears, which made pointer clicks unreliable.
    """
    pilot.app.screen.query_one(selector, Button).press()
    await pilot.pause()
    await pilot.pause()


async def _until(pilot, condition, tries: int = 50) -> None:
    """Wait for something that happens after a dialog's callback has run."""
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _text(app: WorkbenchApp, selector: str) -> str:
    return str(app.query_one(selector, Static).render())


def _rows(app: WorkbenchApp, selector: str) -> list[list[str]]:
    table = app.query_one(selector).query_one(TextualDataTable)
    return [[str(c) for c in table.get_row_at(i)] for i in range(table.row_count)]


def test_overview_without_a_project_says_so_and_how_to_fix_it(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        assert app.query_one("#overview-empty").display
        assert not app.query_one("#overview-metrics").display
        assert "No project is open" in _text(app, "#overview-empty")

    _run(tmp_path, scenario)


def test_overview_shows_the_real_numbers_and_recent_runs(tmp_path: Path) -> None:
    project = ProjectRepository(tmp_path).create("Demo", repository="https://g.test/a")
    repo = repository_for(tmp_path, project)
    case = _case(repo, "Checkout works")
    _execution(repo, case.id, "passed")
    _execution(repo, case.id, "failed")

    async def scenario(app, pilot) -> None:
        assert not app.query_one("#overview-empty").display
        assert "Demo  [PROJ-001]" in _text(app, "#overview-identity")
        assert "https://g.test/a" in _text(app, "#overview-identity")
        for key, expected in {
            "cases": "1",
            "passed": "1",
            "failed": "1",
            "blocked": "0",
        }.items():
            assert _text(app, f"#metric-{key}").endswith(expected), key
        rows = _rows(app, "#overview-recent")
        assert len(rows) == 2 and "TC-001 Checkout works" in rows[0][3]
        assert "FAILED" in rows[0][1] and "PASSED" in rows[1][1]

    _run(tmp_path, scenario, project)


def test_ctrl_r_picks_up_changes_made_outside_the_app(tmp_path: Path) -> None:
    project = ProjectRepository(tmp_path).create("Demo")
    repo = repository_for(tmp_path, project)

    async def scenario(app, pilot) -> None:
        assert _text(app, "#metric-cases").endswith("0")
        _case(repo)
        await pilot.press("ctrl+r")
        assert _text(app, "#metric-cases").endswith("1")

    _run(tmp_path, scenario, project)


def test_damaged_records_are_shown_on_the_overview(tmp_path: Path) -> None:
    project = ProjectRepository(tmp_path).create("Demo")
    repo = repository_for(tmp_path, project)
    _case(repo)
    _case(repo, "Other")
    repo.path_of("TC-002").write_text("garbage", encoding="utf-8")

    async def scenario(app, pilot) -> None:
        assert "1 damaged record(s) are not counted" in _text(app, "#overview-problems")

    _run(tmp_path, scenario, project)


def test_projects_page_lists_and_opens_the_selected_project(tmp_path: Path) -> None:
    projects = ProjectRepository(tmp_path)
    projects.create("First")
    projects.create("Second", repository="https://g.test/b")

    async def scenario(app, pilot) -> None:
        app.navigate("projects")
        await pilot.pause()
        rows = _rows(app, "#projects-table")
        assert [r[0] for r in rows] == ["PROJ-001", "PROJ-002"]
        assert rows[1][4] == "https://g.test/b"

        table = app.query_one("#projects-table").query_one(TextualDataTable)
        table.focus()
        await pilot.press("down", "enter")
        await _until(pilot, lambda: app.project is not None)

        assert app.project is not None and app.project.id == "PROJ-002"
        assert _text(app, "#header-project").startswith("PROJ-002")
        assert "PROJ-002" in _text(app, "#status-bar")
        assert _text(app, "#page-title") == "OVERVIEW"
        assert "Second  [PROJ-002]" in _text(app, "#overview-identity")

    _run(tmp_path, scenario)


def test_new_project_dialog_validates_then_creates_and_opens_it(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("projects")
        await pilot.pause()
        assert "No projects yet" in str(
            app.query_one("#projects-table").query_one(".state-empty").render()
        )
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, FormDialog)

        await _click(pilot, "#submit")  # nothing typed yet
        assert "Required: Name" in _text(app.screen, "#form-error")

        app.screen.query_one("#field-name", Input).value = "Checkout service"
        app.screen.query_one("#field-environment", Input).value = "staging"
        await pilot.pause()
        await _click(pilot, "#submit")  # environment without a URL
        assert "both the environment name and its URL" in _text(
            app.screen, "#form-error"
        )

        app.screen.query_one("#field-url", Input).value = "https://staging.example.com"
        await pilot.pause()
        await _click(pilot, "#submit")
        await _until(pilot, lambda: app.project is not None)

        assert app.project is not None and app.project.name == "Checkout service"
        assert [e.name for e in app.project.environments] == ["staging"]
        assert ProjectRepository(tmp_path).open("PROJ-001").name == "Checkout service"

    _run(tmp_path, scenario)


def test_cancelling_the_dialog_creates_nothing(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("projects")
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)
        assert len(ProjectRepository(tmp_path).list_projects().projects) == 0

    _run(tmp_path, scenario)


def test_archiving_asks_first_and_updates_the_open_project(tmp_path: Path) -> None:
    project = ProjectRepository(tmp_path).create("Old")

    async def scenario(app, pilot) -> None:
        app.navigate("projects")
        await pilot.pause()
        app.query_one("#projects-table").query_one(TextualDataTable).focus()
        await pilot.press("x")
        await pilot.pause()
        await pilot.press("escape")  # cancel: nothing happens
        await pilot.pause()
        assert ProjectRepository(tmp_path).open("PROJ-001").archived is False

        await pilot.press("x")
        await pilot.pause()
        app.screen.query_one("#confirm", Button).press()
        await _until(
            pilot,
            lambda: ProjectRepository(tmp_path).open("PROJ-001").archived,
        )
        assert ProjectRepository(tmp_path).open("PROJ-001").archived is True
        assert app.project is not None and app.project.archived

    _run(tmp_path, scenario, project)


def test_opening_a_project_that_vanished_is_reported(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        app.open_project("PROJ-404")
        await pilot.pause()
        assert app.project is None

    _run(tmp_path, scenario)


def test_damaged_projects_are_listed_as_problems_not_hidden(tmp_path: Path) -> None:
    ProjectRepository(tmp_path).create("Good")
    bad = ProjectRepository(tmp_path).root / "PROJ-002"
    bad.mkdir()
    (bad / "project.yaml").write_text("{not yaml", encoding="utf-8")

    async def scenario(app, pilot) -> None:
        app.navigate("projects")
        await pilot.pause()
        assert "Damaged project" in _text(app, "#projects-problems")
        assert [r[0] for r in _rows(app, "#projects-table")] == ["PROJ-001"]

    _run(tmp_path, scenario)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"environment": "staging", "url": ""}, "both the environment"),
        ({"environment": "", "url": "https://a.test"}, "both the environment"),
        ({"environment": "staging", "url": "ftp://a.test"}, "http"),
        ({"environment": "staging", "url": "https://u:p@a.test"}, "credentials"),
    ],
)
def test_new_project_validation(values, message) -> None:
    assert message in (validate_new_project(values) or "")
    assert validate_new_project({"environment": "", "url": ""}) is None
    assert validate_new_project({"environment": "qa", "url": "https://a.test"}) is None


def test_form_dialog_rejects_bad_definitions() -> None:
    with pytest.raises(ValueError):
        FormDialog("", [FormField("a", "A")])
    with pytest.raises(ValueError):
        FormDialog("T", [])
    with pytest.raises(ValueError, match="unique"):
        FormDialog("T", [FormField("a", "A"), FormField("a", "B")])
    assert DataTable  # the page tables are the shared component
