import asyncio
from pathlib import Path

from textual.widgets import Button, Input, Static

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for


async def _until(pilot, condition, tries: int = 60) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _ai_requirement(repository, title: str = "Users can pay", **extra) -> str:
    fields = {
        "title": title,
        "status": "draft",
        "source": "ai.md",
        "origin": "ai",
        "generated_by": "opencode",
        "ai_findings": [
            {"kind": "fact", "text": "It is about cards", "source": "REQ-001"},
            {"kind": "hypothesis", "text": "Refunds may apply"},
        ],
        **extra,
    }
    return repository.create("REQ", fields, "# Pay\n\nCustomers pay by card.\n").id


def _run(tmp_path: Path, prepare, scenario) -> None:
    project = ProjectRepository(tmp_path).create("Demo")
    repository = repository_for(tmp_path, project)
    prepare(repository)

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate("review")
            await pilot.pause()
            await scenario(app, pilot, repository)

    asyncio.run(runner())


def _text(app, selector: str) -> str:
    """Text of a widget; pages share ids, so look inside the Review page first."""
    pages = app.query("#page-review")
    scope = pages.first() if selector.startswith("#browse") else app
    return str(scope.query_one(selector).render())


async def _decide(app, pilot, key: str, reviewer: str, comment: str = "") -> None:
    await pilot.press(key)
    await _until(pilot, lambda: isinstance(app.screen, FormDialog))
    app.screen.query_one("#field-reviewer", Input).value = reviewer
    app.screen.query_one("#field-comment", Input).value = comment
    app.screen.query_one("#submit", Button).press()
    await pilot.pause()


def test_only_ai_records_waiting_for_a_decision_are_listed_with_what_the_ai_said(
    tmp_path,
) -> None:
    def prepare(repository) -> None:
        _ai_requirement(repository)
        repository.create(
            "REQ",
            {"title": "By hand", "status": "draft", "source": "x", "origin": "manual"},
            "# By hand\n",
        )

    async def scenario(app, pilot, repository) -> None:
        assert "1 record" in _text(app, "#browse-summary")
        detail = _text(app, "#browse-detail")
        assert "FACT" in detail and "[REQ-001]" in detail
        assert "HYPOTHESIS" in detail and "[no source]" in detail
        assert "analysis, not evidence" in detail

    _run(tmp_path, prepare, scenario)


def test_submit_then_approve_records_the_reviewer_and_clears_the_list(tmp_path) -> None:
    async def scenario(app, pilot, repository) -> None:
        await pilot.press("s")
        await _until(
            pilot, lambda: repository.get("REQ-001").metadata["status"] == "in_review"
        )
        await _decide(app, pilot, "a", "Ana", "Looks right")
        await _until(
            pilot, lambda: repository.get("REQ-001").metadata["status"] == "approved"
        )
        review = repository.get("REQ-001").metadata["reviews"][-1]
        assert review["reviewer"] == "Ana" and review["decision"] == "approved"
        await _until(pilot, lambda: "0 record" in _text(app, "#browse-summary"))

    _run(tmp_path, _ai_requirement, scenario)


def test_a_rejection_needs_a_reason_and_keeps_what_was_typed(tmp_path) -> None:
    async def scenario(app, pilot, repository) -> None:
        await pilot.press("s")
        await _until(
            pilot, lambda: repository.get("REQ-001").metadata["status"] == "in_review"
        )
        await _decide(app, pilot, "x", "Ana", "")

        assert isinstance(app.screen, FormDialog)
        assert "Required" in str(app.screen.query_one("#form-error", Static).render())
        assert app.screen.query_one("#field-reviewer", Input).value == "Ana"
        assert repository.get("REQ-001").metadata["status"] == "in_review"

        app.screen.query_one("#field-comment", Input).value = "Out of scope"
        app.screen.query_one("#submit", Button).press()
        await _until(
            pilot, lambda: repository.get("REQ-001").metadata["status"] == "rejected"
        )

    _run(tmp_path, _ai_requirement, scenario)


def test_the_author_cannot_approve_their_own_ai_record(tmp_path) -> None:
    def prepare(repository) -> None:
        _ai_requirement(repository, author="Ana")

    async def scenario(app, pilot, repository) -> None:
        await pilot.press("s")
        await _until(
            pilot, lambda: repository.get("REQ-001").metadata["status"] == "in_review"
        )
        await _decide(app, pilot, "a", "Ana")

        assert isinstance(app.screen, FormDialog)
        assert str(app.screen.query_one("#form-error", Static).render()).strip()
        assert repository.get("REQ-001").metadata["status"] == "in_review"

    _run(tmp_path, prepare, scenario)


def test_the_overview_says_how_many_records_wait(tmp_path) -> None:
    async def scenario(app, pilot, repository) -> None:
        app.navigate("overview")
        await pilot.pause()
        assert "1 AI record(s) waiting" in _text(app, "#overview-review")

    _run(tmp_path, _ai_requirement, scenario)
