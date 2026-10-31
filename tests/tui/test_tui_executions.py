import asyncio
from pathlib import Path

import pytest
from test_tui_data import _case, _execution
from textual.widgets import Button, Input, Static
from textual.widgets import DataTable as TextualDataTable

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.executions.recording import finish_step, start_step
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.browse_executions import (
    allowed_moves,
    execution_detail,
    execution_rows,
)
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.tui.pages.executions import split_ids, validate_new
from qa_workbench.workspace import repository_for


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo")


@pytest.fixture
def repo(tmp_path: Path, project):
    return repository_for(tmp_path, project)


# -- view-models ------------------------------------------------------------------


def test_rows_are_newest_first_with_state_and_case(repo) -> None:
    case = _case(repo, "Checkout works")
    first = _execution(repo, case.id, "passed")
    second = _execution(repo, case.id, "failed")
    third = _execution(repo, case.id, None)

    rows = execution_rows(repo).rows

    assert [r.key for r in rows] == [third.id, second.id, first.id]
    assert rows[0].cells[1:] == ("◷ CREATED", "manual", "Ana", "TC-001 Checkout works")
    assert "✗ FAILED" in rows[1].cells[1] and rows[1].status == "failed"
    assert "staging" in rows[0].search


def test_detail_shows_steps_evidence_and_the_next_states(repo) -> None:
    case = _case(repo)
    record = _execution(repo, case.id, "passed", finalize=False)

    text = execution_detail(repo, record.id)

    assert "TC-001 Log in" in text and "[x] 1. Open the page  ->  seen" in text
    assert "OBSERVED RESULT\n  seen" in text and "EVD-001" in text
    assert "NEXT: finalized" in text


def test_a_running_execution_shows_the_step_in_progress(repo) -> None:
    case = _case(repo)
    record = _execution(repo, case.id, "running")
    start_step(repo, record.id, 1, "Open the page")

    text = execution_detail(repo, record.id)

    assert "[>] 1. Open the page" in text
    assert "Record steps with `batman executions`" in text


def test_a_finalized_execution_is_final(repo) -> None:
    case = _case(repo)
    record = _execution(repo, case.id, "passed")

    assert allowed_moves(repo, record.id) == []
    assert "final, nothing can change it" in execution_detail(repo, record.id)
    assert allowed_moves(repo, _execution(repo, case.id, None).id) == [
        "cancelled",
        "planned",
    ]


def test_damaged_executions_are_reported(repo) -> None:
    case = _case(repo)
    _execution(repo, case.id, None)
    _execution(repo, case.id, None)
    repo.path_of("EXEC-002").write_text("garbage", encoding="utf-8")

    data = execution_rows(repo)

    assert [r.key for r in data.rows] == ["EXEC-001"] and len(data.problems) == 1


def test_helpers() -> None:
    assert split_ids(" EVD-1 , ,EVD-2") == ["EVD-1", "EVD-2"]
    assert validate_new({"type": "manual"}) is None
    assert "Type must be one of" in (validate_new({"type": "ritual"}) or "")


# -- the page ----------------------------------------


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


def _keys(app: WorkbenchApp) -> list[str]:
    table = app.query_one("#page-executions #browse-table").query_one(TextualDataTable)
    return [
        str(table.coordinate_to_cell_key((i, 0)).row_key.value)
        for i in range(table.row_count)
    ]


async def _submit(pilot) -> None:
    pilot.app.screen.query_one("#submit", Button).press()
    await pilot.pause()
    await pilot.pause()


def _fill(app, values: dict[str, str]) -> None:
    for key, value in values.items():
        app.screen.query_one(f"#field-{key}", Input).value = value


def test_start_and_run_an_execution_through_its_lifecycle(
    tmp_path, project, repo
) -> None:
    _case(repo)
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    evidence = EvidenceStore(repo).register(shot, source="manual", description="proof")

    async def scenario(app, pilot) -> None:
        app.navigate("executions")
        await pilot.pause()
        assert "Press N to start" in str(
            app.query_one("#page-executions").query_one(".state-empty").render()
        )
        await pilot.press("n")
        await pilot.pause()
        _fill(app, {"case": "TC-404", "executor": "Ana", "environment": "staging"})
        await pilot.pause()
        await _submit(pilot)
        assert isinstance(app.screen, FormDialog)
        assert "TC-404" in _text(app.screen, "#form-error")

        _fill(app, {"case": "TC-001"})
        await pilot.pause()
        await _submit(pilot)
        await _until(pilot, lambda: _keys(app) == ["EXEC-001"])

        for target in ("planned", "running"):
            await pilot.press("m")
            await pilot.pause()
            _fill(app, {"target": target})
            await pilot.pause()
            await _submit(pilot)
            await _until(
                pilot, lambda t=target: repo.get("EXEC-001").metadata["status"] == t
            )

        start_step(repo, "EXEC-001", 1, "Open the page")
        finish_step(repo, "EXEC-001", 1, "passed", observed="seen")

        await pilot.press("m")
        await pilot.pause()
        _fill(app, {"target": "paused"})  # not a state it can move to from running
        await pilot.pause()
        await _submit(pilot)
        assert "can move to" in _text(app.screen, "#form-error")

        _fill(app, {"target": "passed", "observed": "The dashboard is shown"})
        await pilot.pause()
        await _submit(pilot)  # a passed execution needs evidence
        assert "evidence" in _text(app.screen, "#form-error").lower()

        _fill(app, {"evidence": evidence.id})
        await pilot.pause()
        await _submit(pilot)
        await _until(pilot, lambda: repo.get("EXEC-001").metadata["status"] == "passed")

        await pilot.press("m")
        await pilot.pause()
        _fill(app, {"target": "finalized"})
        await pilot.pause()
        await _submit(pilot)
        await _until(
            pilot, lambda: repo.get("EXEC-001").metadata["status"] == "finalized"
        )
        assert "final, nothing can change it" in _text(
            app.query_one("#page-executions"), "#browse-detail"
        )
        await pilot.press("m")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)  # nothing left to do

    _run(tmp_path, scenario, project)


def test_moving_needs_a_selected_execution(tmp_path, project) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("executions")
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)

    _run(tmp_path, scenario, project)


def test_archived_projects_cannot_start_or_move_executions(
    tmp_path, project, repo
) -> None:
    _execution(repo, _case(repo).id, None)
    archived = ProjectRepository(tmp_path).archive(project.id)

    async def scenario(app, pilot) -> None:
        app.navigate("executions")
        await pilot.pause()
        assert _keys(app) == ["EXEC-001"]
        for key in ("n", "m"):
            await pilot.press(key)
            await pilot.pause()
            assert not isinstance(app.screen, FormDialog), key

    _run(tmp_path, scenario, archived)
