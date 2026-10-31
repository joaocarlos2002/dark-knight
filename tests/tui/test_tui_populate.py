import asyncio
import json

from qa_workbench.ai import cli as ai_cli
from qa_workbench.ai.alfred import AlfredSettings, save_settings
from qa_workbench.ai.http import JsonResponse
from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.workspace import repository_for

CASES = {
    "cases": [
        {
            "title": "Pay with a card",
            "objective": "A customer pays",
            "steps": [{"action": "Pay", "expected": "Paid"}],
            "expected_result": "The order is paid",
        }
    ]
}


class Http:
    """A tiny Ollama that always answers with one test case."""

    def __init__(self) -> None:
        self.chats = 0

    def request(self, method, url, *, body=None, headers=None, timeout=30.0):
        if url.endswith("/api/version"):
            return JsonResponse(200, {"version": "0.5.1"}, {})
        self.chats += 1
        message = {"role": "assistant", "content": json.dumps(CASES)}
        return JsonResponse(200, {"model": "m", "message": message}, {})

    def stream_lines(self, *args, **kwargs):  # pragma: no cover - not used
        raise AssertionError("populate does not stream")


async def _until(pilot, condition, tries: int = 100) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _text(app, selector: str) -> str:
    return str(app.query_one("#page-overview").query_one(selector).render())


def test_p_asks_before_starting_and_then_creates_review_drafts(
    tmp_path, monkeypatch
) -> None:
    project = ProjectRepository(tmp_path).create("Demo")
    repository = repository_for(tmp_path, project)
    repository.create(
        "REQ",
        {
            "title": "Pay by card",
            "status": "approved",
            "source": "r",
            "origin": "manual",
        },
        "# Pay\n",
    )
    save_settings(repository.root, AlfredSettings(engine="own", model="m"))
    http = Http()
    monkeypatch.setattr(ai_cli, "default_http", lambda: http)

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate("overview")
            await pilot.pause()
            assert "no test case" in _text(app, "#overview-review")

            await pilot.press("p")
            await _until(pilot, lambda: isinstance(app.screen, ConfirmationDialog))
            assert http.chats == 0  # nothing is asked until the person says yes
            app.screen.query_one("#confirm").press()
            await _until(pilot, lambda: repository.list_records("TC").records)
            meta = repository.get("TC-001").metadata
            assert meta["status"] == "draft" and meta["origin"] == "ai"
            await _until(
                pilot,
                lambda: any("draft case" in n.message for n in app._notifications),
            )
            await _until(
                pilot,
                lambda: "waiting for your review" in _text(app, "#overview-review"),
            )

    asyncio.run(runner())
