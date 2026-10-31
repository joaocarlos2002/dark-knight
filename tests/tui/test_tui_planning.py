import asyncio
from pathlib import Path

import pytest
from test_tui_data import _case, _execution
from textual.widgets import Button, Input, Static
from textual.widgets import DataTable as TextualDataTable

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.plans.builder import PlanDraft, create_plan, set_selection
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.suites.service import create_suite
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.browse_planning import (
    plan_detail,
    plan_rows,
    suite_detail,
    suite_rows,
)
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.tui.pages.plans import draft_from, split
from qa_workbench.tui.pages.suites import split_ids, validate_new_suite
from qa_workbench.workspace import repository_for


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo")


@pytest.fixture
def repo(tmp_path: Path, project):
    return repository_for(tmp_path, project)


def _plan(repo, title="Release 1.5", **extra):
    values = {
        "title": title,
        "scope": "Login and checkout",
        "strategy": "Smoke then regression",
        "objectives": ["Validate changed flows"],
        "entry_criteria": ["Build deployed"],
        "exit_criteria": ["No critical defect"],
        **extra,
    }
    return create_plan(repo, PlanDraft(**values))


# -- view-models --------------------------------------------------------------------


def test_suite_rows_and_detail_with_members_estimate_and_last_run(repo) -> None:
    login = _case(repo, "Login")
    pay = _case(repo, "Pay")
    repo.update(login.id, {"estimated_minutes": 5})
    suite = create_suite(
        repo, "Smoke", "smoke", cases=[login.id, pay.id], tags=["core"]
    )
    _execution(repo, login.id, "passed")

    row = suite_rows(repo).rows[0]
    text = suite_detail(repo, suite.id)

    assert row.cells == (suite.id, "smoke", "draft", "2", "Smoke")
    assert "core" in row.search
    assert f"{login.id}  Login [active]" in text
    assert "Total: 2 case(s)" in text
    assert "5 min (only 1 of 2 cases have an estimate)" in text
    assert "Last execution: EXEC-001 (passed)" in text


def test_a_suite_with_nothing_says_so(repo) -> None:
    suite = create_suite(repo, "Empty", "custom")

    text = suite_detail(repo, suite.id)

    assert "(no cases yet)" in text and "no estimates recorded" in text
    assert "Last execution: none recorded" in text and "(no description)" in text


def test_a_missing_member_is_flagged(repo) -> None:
    case = _case(repo)
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])
    repo.path_of(case.id).unlink()

    text = suite_detail(repo, suite.id)

    assert (
        "(record not found)" in text
        and "WARNING: TC-001 named here but missing" in text
    )


def test_plan_rows_and_detail(repo) -> None:
    case = _case(repo, "Login")
    suite = create_suite(repo, "Smoke", "smoke", cases=[case.id])
    plan = _plan(repo, suites=[suite.id], risks=[])
    set_selection(
        repo,
        plan.id,
        [
            {
                "id": case.id,
                "decision": "include",
                "reasons": [{"factor": "criticality", "detail": "marked high"}],
            },
            {
                "id": "TC-009",
                "decision": "exclude",
                "reasons": [{"factor": "time", "detail": "out of budget"}],
            },
        ],
    )

    row = plan_rows(repo).rows[0]
    text = plan_detail(repo, plan.id)

    assert row.cells == (plan.id, "draft", "1", "1", "Release 1.5")
    assert "Login and checkout" in text and "  - Validate changed flows" in text
    assert f"{suite.id}  Smoke (1 cases)" in text
    assert "1 included, 1 excluded" in text and "+ TC-001  marked high" in text


def test_a_plan_without_a_selection_points_to_the_command(repo) -> None:
    plan = _plan(repo)

    text = plan_detail(repo, plan.id)

    assert "no selection yet" in text and "batman plans recommend" in text


def test_damaged_suites_and_plans_are_reported(repo) -> None:
    create_suite(repo, "Good", "smoke")
    create_suite(repo, "Bad", "smoke")
    repo.path_of("SUITE-002").write_text("garbage", encoding="utf-8")
    _plan(repo)
    _plan(repo, "Bad plan")
    repo.path_of("TP-002").write_text("garbage", encoding="utf-8")

    suites, plans = suite_rows(repo), plan_rows(repo)

    assert [r.key for r in suites.rows] == ["SUITE-001"] and len(suites.problems) == 1
    assert [r.key for r in plans.rows] == ["TP-001"] and len(plans.problems) == 1


# -- pages ---------------------------------------------------------------


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


def _keys(app: WorkbenchApp, key: str) -> list[str]:
    table = app.query_one(f"#page-{key} #browse-table").query_one(TextualDataTable)
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


def test_the_suites_page_lists_and_describes(tmp_path, project, repo) -> None:
    case = _case(repo, "Login")
    create_suite(repo, "Smoke", "smoke", cases=[case.id])

    async def scenario(app, pilot) -> None:
        app.navigate("test-suites")
        await pilot.pause()
        assert _keys(app, "test-suites") == ["SUITE-001"]
        assert "TC-001  Login" in _text(
            app.query_one("#page-test-suites"), "#browse-detail"
        )

    _run(tmp_path, scenario, project)


def test_new_suite_validates_then_creates_and_cases_can_be_added_and_removed(
    tmp_path, project, repo
) -> None:
    _case(repo, "Login")
    _case(repo, "Pay")

    async def scenario(app, pilot) -> None:
        app.navigate("test-suites")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert isinstance(app.screen, FormDialog)

        _fill(app, {"title": "Smoke", "type": "sanity-ish"})
        await pilot.pause()
        await _submit(pilot)
        assert "Type must be one of" in _text(app.screen, "#form-error")

        _fill(app, {"type": "smoke", "cases": "TC-001, TC-404"})
        await pilot.pause()
        await _submit(pilot)
        assert isinstance(app.screen, FormDialog) and "TC-404" in _text(
            app.screen, "#form-error"
        )

        _fill(app, {"cases": "TC-001"})
        await pilot.pause()
        await _submit(pilot)
        await _until(pilot, lambda: _keys(app, "test-suites") == ["SUITE-001"])
        assert repo.get("SUITE-001").metadata["cases"] == ["TC-001"]

        app.query_one("#page-test-suites").focus_primary()
        await pilot.press("a")
        await pilot.pause()
        _fill(app, {"cases": "TC-001"})  # already a member
        await pilot.pause()
        await _submit(pilot)
        assert "already contains" in _text(app.screen, "#form-error")
        _fill(app, {"cases": "TC-002"})
        await pilot.pause()
        await _submit(pilot)
        await _until(
            pilot,
            lambda: repo.get("SUITE-001").metadata["cases"] == ["TC-001", "TC-002"],
        )

        await pilot.press("r")
        await pilot.pause()
        _fill(app, {"cases": "TC-002"})
        await pilot.pause()
        await _submit(pilot)
        await _until(
            pilot, lambda: repo.get("SUITE-001").metadata["cases"] == ["TC-001"]
        )

    _run(tmp_path, scenario, project)


def test_adding_cases_needs_a_selected_suite(tmp_path, project) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("test-suites")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)

    _run(tmp_path, scenario, project)


def test_new_plan_checks_suites_and_creates_a_draft(tmp_path, project, repo) -> None:
    create_suite(repo, "Smoke", "smoke")

    async def scenario(app, pilot) -> None:
        app.navigate("test-plans")
        await pilot.pause()
        assert "Press N to write" in str(
            app.query_one("#page-test-plans").query_one(".state-empty").render()
        )
        await pilot.press("n")
        await pilot.pause()
        await _submit(pilot)
        assert "Required" in _text(app.screen, "#form-error")

        _fill(
            app,
            {
                "title": "Release 1.5",
                "scope": "Login",
                "strategy": "Smoke first",
                "objectives": "Validate; Report",
                "entry": "Build deployed",
                "exit": "No critical defect",
                "suites": "SUITE-001, SUITE-404",
            },
        )
        await pilot.pause()
        await _submit(pilot)
        assert "Unknown suite(s): SUITE-404" in _text(app.screen, "#form-error")

        _fill(app, {"suites": "SUITE-001"})
        await pilot.pause()
        await _submit(pilot)
        await _until(pilot, lambda: _keys(app, "test-plans") == ["TP-001"])
        plan = repo.get("TP-001")
        assert plan.metadata["objectives"] == ["Validate", "Report"]
        assert plan.metadata["suites"] == ["SUITE-001"]
        assert "Release 1.5" in _text(
            app.query_one("#page-test-plans"), "#browse-detail"
        )

    _run(tmp_path, scenario, project)


def test_archived_projects_cannot_change_suites_or_plans(
    tmp_path, project, repo
) -> None:
    create_suite(repo, "Smoke", "smoke")
    archived = ProjectRepository(tmp_path).archive(project.id)

    async def scenario(app, pilot) -> None:
        app.navigate("test-suites")
        await pilot.pause()
        assert _keys(app, "test-suites") == ["SUITE-001"]
        for key in ("n", "a", "r"):
            await pilot.press(key)
            await pilot.pause()
            assert not isinstance(app.screen, FormDialog), key
        app.navigate("test-plans")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)

    _run(tmp_path, scenario, archived)


def test_helpers() -> None:
    assert split_ids(" TC-1 , ,TC-2") == ["TC-1", "TC-2"]
    assert split("a; b;;c ", ";") == ["a", "b", "c"]
    assert validate_new_suite({"type": "smoke"}) is None
    values = {
        "title": "T",
        "scope": "S",
        "strategy": "X",
        "objectives": "o1; o2",
        "entry": "e",
        "exit": "x",
        "suites": "",
    }
    draft = draft_from(values)
    assert draft.objectives == ["o1", "o2"] and draft.suites == []
