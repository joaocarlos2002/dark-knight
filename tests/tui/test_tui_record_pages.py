import asyncio
from pathlib import Path

import pytest
from test_tui_browse import _requirement
from test_tui_data import _case
from textual.widgets import Button, Input, Static
from textual.widgets import DataTable as TextualDataTable

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.tui.pages.cases import draft_from, parse_steps, validate_new_case
from qa_workbench.workspace import repository_for


def _run(data_dir: Path, scenario, project=None, size=(140, 55)) -> None:
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


async def _until(pilot, condition, tries: int = 60) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _text(widget, selector: str) -> str:
    return str(widget.query_one(selector, Static).render())


def _page(app: WorkbenchApp, key: str):
    return app.query_one(f"#page-{key}")


def _keys(app: WorkbenchApp, key: str) -> list[str]:
    table = _page(app, key).query_one("#browse-table").query_one(TextualDataTable)
    return [
        str(table.coordinate_to_cell_key((i, 0)).row_key.value)
        for i in range(table.row_count)
    ]


async def _submit(pilot) -> None:
    pilot.app.screen.query_one("#submit", Button).press()
    await pilot.pause()
    await pilot.pause()


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo")


@pytest.fixture
def repo(tmp_path: Path, project):
    return repository_for(tmp_path, project)


def test_pages_without_a_project_say_so(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        for key in ("requirements", "test-cases"):
            app.navigate(key)
            await pilot.pause()
            assert "No project is open" in _text(_page(app, key), "#browse-summary")

    _run(tmp_path, scenario)


def test_requirements_list_search_filter_and_detail(tmp_path, project, repo) -> None:
    first = _requirement(
        repo, "Users can log in", acceptance_criteria=["Valid password"]
    )
    _requirement(repo, "Users can log out", status="draft")
    case = _case(repo, "Valid login")
    repo.update(case.id, {"requirements": [first.id]})

    async def scenario(app, pilot) -> None:
        app.navigate("requirements")
        await pilot.pause()
        assert _keys(app, "requirements") == ["REQ-001", "REQ-002"]
        assert "2 requirement(s)" in _text(
            _page(app, "requirements"), "#browse-summary"
        )
        detail = _text(_page(app, "requirements"), "#browse-detail")
        assert "Users can log in" in detail and "  - Valid password" in detail
        assert "TC-001  Valid login" in detail

        search = _page(app, "requirements").query_one("#browse-search", Input)
        search.value = "out"
        await pilot.pause()
        assert _keys(app, "requirements") == ["REQ-002"]
        assert "1 of 2" in _text(_page(app, "requirements"), "#browse-summary")
        assert "NOT COVERED" not in _text(_page(app, "requirements"), "#browse-detail")
        assert "no test case covers this" in _text(
            _page(app, "requirements"), "#browse-detail"
        )

        search.value = ""
        _page(app, "requirements").focus()
        await pilot.press("f")  # filter: all -> approved
        await pilot.pause()
        assert _keys(app, "requirements") == ["REQ-001"]
        await pilot.press("f", "f")  # draft, then back to all
        await pilot.pause()
        assert _keys(app, "requirements") == ["REQ-001", "REQ-002"]

    _run(tmp_path, scenario, project)


def test_moving_the_cursor_changes_the_detail(tmp_path, project, repo) -> None:
    _requirement(repo, "First one")
    _requirement(repo, "Second one")

    async def scenario(app, pilot) -> None:
        app.navigate("requirements")
        await pilot.pause()
        assert "First one" in _text(_page(app, "requirements"), "#browse-detail")
        await pilot.press("down")
        await _until(
            pilot,
            lambda: "Second one" in _text(_page(app, "requirements"), "#browse-detail"),
        )

    _run(tmp_path, scenario, project)


def test_ctrl_k_goes_to_the_search_of_the_visible_page(tmp_path, project, repo) -> None:
    _requirement(repo)

    async def scenario(app, pilot) -> None:
        app.navigate("requirements")
        await pilot.pause()
        await pilot.press("ctrl+k")
        assert app.focused is _page(app, "requirements").query_one("#browse-search")
        app.navigate("overview")  # no search field on this page
        await pilot.pause()
        await pilot.press("ctrl+k")
        assert app.focused is not _page(app, "requirements").query_one("#browse-search")

    _run(tmp_path, scenario, project)


def test_empty_pages_explain_what_to_do(tmp_path, project) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("requirements")
        await pilot.pause()
        assert "Press I to import" in str(
            _page(app, "requirements").query_one(".state-empty").render()
        )
        app.navigate("test-cases")
        await pilot.pause()
        assert "Press N to write" in str(
            _page(app, "test-cases").query_one(".state-empty").render()
        )

    _run(tmp_path, scenario, project)


def test_damaged_records_are_shown_under_the_list(tmp_path, project, repo) -> None:
    _case(repo)
    _case(repo, "Broken")
    repo.path_of("TC-002").write_text("garbage", encoding="utf-8")

    async def scenario(app, pilot) -> None:
        app.navigate("test-cases")
        await pilot.pause()
        assert _keys(app, "test-cases") == ["TC-001"]
        assert "1 damaged record(s) are not listed" in _text(
            _page(app, "test-cases"), "#browse-problems"
        )

    _run(tmp_path, scenario, project)


def test_import_reads_a_file_and_reports_what_happened(tmp_path, project, repo) -> None:
    source = tmp_path / "requirements.md"
    source.write_text(
        "## Users can log in\n\nPriority: high\n\n"
        "Acceptance criteria:\n- Valid password\n",
        encoding="utf-8",
    )

    async def scenario(app, pilot) -> None:
        app.navigate("requirements")
        await pilot.pause()
        await pilot.press("i")
        await pilot.pause()
        assert isinstance(app.screen, FormDialog)

        app.screen.query_one("#field-path", Input).value = str(tmp_path / "missing.md")
        await pilot.pause()
        await _submit(pilot)
        assert "is not a file" in _text(app.screen, "#form-error")

        app.screen.query_one("#field-path", Input).value = str(source)
        app.screen.query_one("#field-author", Input).value = "Ana"
        await pilot.pause()
        await _submit(pilot)
        await _until(pilot, lambda: _keys(app, "requirements") == ["REQ-001"])
        assert not isinstance(app.screen, FormDialog)
        assert "Valid password" in _text(_page(app, "requirements"), "#browse-detail")
        assert repo.get("REQ-001").metadata["author"] == "Ana"

    _run(tmp_path, scenario, project)


def test_new_test_case_validates_inside_the_dialog_then_creates(
    tmp_path, project, repo
) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("test-cases")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, FormDialog)

        await _submit(pilot)
        assert "Required" in _text(app.screen, "#form-error")

        fill = {
            "title": "Customer can log in",
            "objective": "Validate login",
            "steps": "Open the page => Form shown; Submit => Dashboard shown",
            "expected": "The user is authenticated",
            "priority": "urgent",
        }
        for key, value in fill.items():
            app.screen.query_one(f"#field-{key}", Input).value = value
        await pilot.pause()
        await _submit(pilot)
        assert "Priority must be one of" in _text(app.screen, "#form-error")

        app.screen.query_one("#field-priority", Input).value = "high"
        app.screen.query_one("#field-requirements", Input).value = "REQ-404"
        await pilot.pause()
        await _submit(pilot)
        assert isinstance(
            app.screen, FormDialog
        )  # the unknown requirement keeps it open
        assert "REQ-404" in _text(app.screen, "#form-error")
        assert (
            app.screen.query_one("#field-title", Input).value == "Customer can log in"
        )

        app.screen.query_one("#field-requirements", Input).value = ""
        await pilot.pause()
        await _submit(pilot)
        await _until(pilot, lambda: _keys(app, "test-cases") == ["TC-001"])
        record = repo.get("TC-001")
        assert (
            record.metadata["status"] == "draft"
            and record.metadata["priority"] == "high"
        )
        assert [s["action"] for s in record.metadata["steps"]] == [
            "Open the page",
            "Submit",
        ]

    _run(tmp_path, scenario, project)


def test_archived_projects_are_read_only(tmp_path, project, repo) -> None:
    _case(repo)
    archived = ProjectRepository(tmp_path).archive(project.id)

    async def scenario(app, pilot) -> None:
        app.navigate("test-cases")
        await pilot.pause()
        assert _keys(app, "test-cases") == ["TC-001"]  # still readable
        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)
        await pilot.press("i")  # on this page "i" does nothing at all
        assert len(repo.list_records("TC").records) == 1

    _run(tmp_path, scenario, archived)


def test_step_and_draft_parsing() -> None:
    steps = parse_steps("Open => Form; Submit ;  ; Check => Done")
    assert [(s.action, s.expected) for s in steps] == [
        ("Open", "Form"),
        ("Submit", ""),
        ("Check", "Done"),
    ]
    values = {"title": "T", "objective": "O", "steps": "a", "expected": "E",
              "priority": "", "requirements": " REQ-001 , ,REQ-002"}  # fmt: skip
    draft = draft_from(values)
    assert draft.priority == "medium" and draft.requirements == ["REQ-001", "REQ-002"]
    assert validate_new_case({**values, "steps": " ; "}) == "Give at least one step."
    assert validate_new_case(values) is None
