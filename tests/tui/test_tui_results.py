import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Static
from textual.widgets import DataTable as TextualDataTable

from qa_workbench.api.models import Exchange, FlowResult, StepResult
from qa_workbench.api.records import save_flow
from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.bughunt.service import reclassify, record_finding
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.release.records import COMPLETED
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, ApprovalBook, ApprovalRequired
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import SecuritySettings
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.browse_results import (
    api_detail,
    api_rows,
    bug_detail,
    bug_rows,
    release_detail,
    release_rows,
    security_detail,
    security_rows,
)
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for


@pytest.fixture
def project(tmp_path: Path):
    return ProjectRepository(tmp_path).create("Demo")


@pytest.fixture
def repo(tmp_path: Path, project):
    return repository_for(tmp_path, project)


def _bug(repo, title="Odd flicker"):
    return record_finding(repo, title=title, environment="staging", found_by="Ana")


def _api(repo):
    exchange = Exchange("GET", "https://api.test/me", {}, "", 200, {}, "{}", 12.0)
    flow = FlowResult(
        "Users API",
        "https://api.test",
        (
            StepResult("login", "passed", (), exchange),
            StepResult("profile", "failed", (), exchange),
        ),
    )
    return save_flow(repo, flow)


def _release(repo):
    return repo.create(
        "REL",
        {
            "status": COMPLETED,
            "title": "Release analysis (ref main)",
            "scope": "ref main",
            "risk_level": "high",
            "commits": ["a" * 40, "b" * 40],
        },
        "# Release analysis\n\n## Risk areas\n\nsrc/auth is high.\n",
    )


def _ask_for_approval(repo) -> str:
    guard = ActionGuard(SecuritySettings(), AuditLog(repo.root))
    action = ActionRequest("post comment", Category.EXTERNAL_COMMENT, "Result for #7")
    with pytest.raises(ApprovalRequired) as asked:
        guard.authorize(action)
    return asked.value.request_id


# -- view-models --------------------


def test_bug_rows_and_detail_with_history(repo) -> None:
    bug = _bug(repo)
    reclassify(repo, bug.id, "inconclusive", by="Ana", justification="could not repeat")

    row = bug_rows(repo).rows[0]
    text = bug_detail(repo, bug.id)

    assert row.cells == (bug.id, "inconclusive", "0/1", "-", "Odd flicker")
    assert "Found by Ana" in text and "CLASSIFICATION HISTORY" in text
    assert "suspected -> inconclusive by Ana: could not repeat" in text


def test_api_rows_count_passed_steps(repo) -> None:
    record = _api(repo)

    row = api_rows(repo).rows[0]

    assert row.cells == (record.id, "failed", "1/2", "Users API")
    assert "sanitized" in api_detail(repo, record.id)
    assert "https://api.test" in row.search


def test_release_rows_and_detail(repo) -> None:
    record = _release(repo)

    row = release_rows(repo).rows[0]

    assert row.cells == (record.id, "high", "2", "Release analysis (ref main)")
    assert "src/auth is high." in release_detail(repo, record.id)


def test_security_rows_mix_approvals_and_checks(repo) -> None:
    request_id = _ask_for_approval(repo)

    data = security_rows(repo)

    assert [r.key for r in data.rows] == [request_id]
    assert data.rows[0].cells[1:3] == ("approval", "pending")
    text = security_detail(repo, request_id)
    assert "PENDING" in text and "A approves, D denies" in text
    assert "once, for one hour" in text
    assert "not found" in security_detail(repo, "APR-ffffffff")


def test_a_tampered_audit_log_is_a_problem_not_an_empty_list(repo) -> None:
    _ask_for_approval(repo)
    log = AuditLog(repo.root)
    log.path.write_text(
        log.path.read_text(encoding="utf-8").replace("post", "POST"), encoding="utf-8"
    )

    data = security_rows(repo)

    assert data.rows == () and data.problems[0].startswith("audit log:")


def test_damaged_result_records_are_reported(repo) -> None:
    _bug(repo)
    _bug(repo, "Other")
    repo.path_of("BUG-002").write_text("garbage", encoding="utf-8")

    data = bug_rows(repo)

    assert [r.key for r in data.rows] == ["BUG-001"] and len(data.problems) == 1


# -- pages --------------------


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


def test_the_result_pages_list_what_the_cli_saved(tmp_path, project, repo) -> None:
    _bug(repo)
    _api(repo)
    _release(repo)

    async def scenario(app, pilot) -> None:
        for page, expected in (
            ("bug-hunting", ["BUG-001"]),
            ("api-testing", ["API-001"]),
            ("release-analysis", ["REL-001"]),
        ):
            app.navigate(page)
            await pilot.pause()
            assert _keys(app, page) == expected, page
        assert "src/auth is high." in _text(
            app.query_one("#page-release-analysis"), "#browse-detail"
        )

    _run(tmp_path, scenario, project)


def test_empty_result_pages_say_how_to_fill_them(tmp_path, project) -> None:
    async def scenario(app, pilot) -> None:
        for page, command in (
            ("bug-hunting", "Press N to record"),
            ("api-testing", "Press R to choose"),
            ("release-analysis", "Press R to read"),
            ("security", "T runs them"),
        ):
            app.navigate(page)
            await pilot.pause()
            empty = str(
                app.query_one(f"#page-{page}").query_one(".state-empty").render()
            )
            assert command in empty, page

    _run(tmp_path, scenario, project)


def test_a_person_approves_a_request_from_the_security_page(
    tmp_path, project, repo
) -> None:
    request_id = _ask_for_approval(repo)

    async def scenario(app, pilot) -> None:
        app.navigate("security")
        await pilot.pause()
        assert _keys(app, "security") == [request_id]
        assert "Audit log intact: 1 entries." in _text(
            app.query_one("#page-security"), "#browse-summary"
        )

        await pilot.press("a")
        await pilot.pause()
        assert isinstance(app.screen, FormDialog)
        await _submit(pilot)  # no name given
        assert "Required" in _text(app.screen, "#form-error")

        app.screen.query_one("#field-by", Input).value = "Agent"  # the requester
        await pilot.pause()
        await _submit(pilot)
        assert "cannot also decide" in _text(app.screen, "#form-error")

        app.screen.query_one("#field-by", Input).value = "Ana"
        app.screen.query_one("#field-reason", Input).value = "Looks right"
        await pilot.pause()
        await _submit(pilot)
        await _until(
            pilot,
            lambda: (
                ApprovalBook(AuditLog(repo.root)).get(request_id).status == "approved"
            ),
        )
        approval = ApprovalBook(AuditLog(repo.root)).get(request_id)
        assert approval.decided_by == "Ana" and approval.reason == "Looks right"
        assert "APPROVED" in _text(app.query_one("#page-security"), "#browse-detail")

        await pilot.press("a")  # already decided
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)

    _run(tmp_path, scenario, project)


def test_denying_needs_a_reason(tmp_path, project, repo) -> None:
    request_id = _ask_for_approval(repo)

    async def scenario(app, pilot) -> None:
        app.navigate("security")
        await pilot.pause()
        await pilot.press("d")
        await pilot.pause()
        app.screen.query_one("#field-by", Input).value = "Ana"
        await pilot.pause()
        await _submit(pilot)
        assert "Required: Reason" in _text(app.screen, "#form-error")

        app.screen.query_one("#field-reason", Input).value = "Wrong environment"
        await pilot.pause()
        await _submit(pilot)
        await _until(
            pilot,
            lambda: (
                ApprovalBook(AuditLog(repo.root)).get(request_id).status == "denied"
            ),
        )

    _run(tmp_path, scenario, project)


def test_an_archived_project_cannot_be_decided_on(tmp_path, project, repo) -> None:
    _ask_for_approval(repo)
    archived = ProjectRepository(tmp_path).archive(project.id)

    async def scenario(app, pilot) -> None:
        app.navigate("security")
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()
        assert not isinstance(app.screen, FormDialog)

    _run(tmp_path, scenario, archived)
