import asyncio
from pathlib import Path

import pytest
from test_tui_browse import _requirement
from test_tui_data import _case
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Input, Static

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.storage.index import RecordIndex
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.workspace import repository_for


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo")


@pytest.fixture
def repo(tmp_path: Path, project):
    return repository_for(tmp_path, project)


def _run(data_dir: Path, scenario, project=None, size=(140, 55)) -> None:
    async def runner() -> None:
        app = WorkbenchApp(
            project,
            preview_channel=PreviewChannel(data_dir / "preview"),
            data_dir=data_dir,
        )
        async with app.run_test(size=(140, 55)) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(runner())


async def _until(pilot, condition, tries: int = 60) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _page(app):
    return app.query_one("#page-knowledge-base")


def _text(app, selector: str) -> str:
    return str(_page(app).query_one(selector, Static).render())


def _keys(app) -> list[str]:
    table = _page(app).query_one("#kb-results").query_one(TextualDataTable)
    return [
        str(table.coordinate_to_cell_key((i, 0)).row_key.value)
        for i in range(table.row_count)
    ]


async def _search(app, pilot, text: str) -> None:
    box = _page(app).query_one("#kb-search", Input)
    box.value = text
    box.focus()
    await pilot.press("enter")
    await pilot.pause()
    await pilot.pause()


def test_without_a_project_it_says_so(tmp_path: Path) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("knowledge-base")
        await pilot.pause()
        assert "No project is open" in _text(app, "#kb-summary")

    _run(tmp_path, scenario)


def test_an_unbuilt_index_is_explained_and_b_builds_it(tmp_path, project, repo) -> None:
    _requirement(repo, "Customers can pay by card")

    async def scenario(app, pilot) -> None:
        app.navigate("knowledge-base")
        await pilot.pause()
        assert "index is not built yet" in _text(app, "#kb-summary")
        assert not RecordIndex(repo).exists

        _page(app).focus()
        await pilot.press("b")
        await _until(pilot, lambda: RecordIndex(repo).exists)
        await pilot.pause()
        assert "index up to date" in _text(app, "#kb-summary")

    _run(tmp_path, scenario, project)


def test_search_finds_records_of_every_kind_with_their_text(
    tmp_path, project, repo
) -> None:
    _requirement(repo, "Customers can pay by card")
    _case(repo, "Valid card payment")
    _case(repo, "Customer can log out")
    RecordIndex(repo).rebuild()

    async def scenario(app, pilot) -> None:
        app.navigate("knowledge-base")
        await pilot.pause()
        await _search(app, pilot, "card")
        assert sorted(_keys(app)) == ["REQ-001", "TC-001"]
        assert "Match:" in _text(app, "#kb-detail")

        await _search(app, pilot, "zzzz")
        assert _keys(app) == [] and "Nothing matches 'zzzz'" in _text(app, "#kb-detail")

        await _search(app, pilot, "   ")
        assert _keys(app) == []

    _run(tmp_path, scenario, project)


def test_the_kind_filter_narrows_the_results(tmp_path, project, repo) -> None:
    _requirement(repo, "Customers can pay by card")
    _case(repo, "Valid card payment")
    RecordIndex(repo).rebuild()

    async def scenario(app, pilot) -> None:
        app.navigate("knowledge-base")
        await pilot.pause()
        await _search(app, pilot, "card")
        assert len(_keys(app)) == 2
        _page(app).focus()
        seen = set()
        for _ in range(12):
            await pilot.press("f")
            await pilot.pause()
            kind = _text(app, "#kb-summary").split("kind: ")[1].split(" ")[0]
            seen.add(kind)
            if kind == "REQ":
                break
        await _search(app, pilot, "card")
        assert _keys(app) == ["REQ-001"] and "REQ" in seen

    _run(tmp_path, scenario, project)


def test_new_records_are_picked_up_on_refresh(tmp_path, project, repo) -> None:
    _requirement(repo, "First one")
    RecordIndex(repo).rebuild()

    async def scenario(app, pilot) -> None:
        app.navigate("knowledge-base")
        await pilot.pause()
        _requirement(repo, "Refunds are possible")
        await pilot.press("ctrl+r")
        await pilot.pause()
        await _search(app, pilot, "refunds")
        assert _keys(app) == ["REQ-002"]

    _run(tmp_path, scenario, project)


def test_a_damaged_index_is_an_error_not_an_empty_result(
    tmp_path, project, repo
) -> None:
    _requirement(repo, "Customers can pay by card")
    index = RecordIndex(repo)
    index.rebuild()
    index.path.write_bytes(b"not a database at all")

    async def scenario(app, pilot) -> None:
        app.navigate("knowledge-base")
        await pilot.pause()
        assert "Search is unavailable" in _text(app, "#kb-summary")

    _run(tmp_path, scenario, project)
