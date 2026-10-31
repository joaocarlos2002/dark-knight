import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import Button, Input

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayResponse
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.settings import SecuritySettings, save_settings
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for

ISSUES = "/api/v4/projects/nees%2Fapp/issues"


class Gateway:
    """A tiny GitLab that can create one test case."""

    def __init__(self) -> None:
        self.writes: list[dict] = []

    def get(self, request):
        return GatewayResponse(200, {}, b"[]")

    def post(self, request):
        self.writes.append(request.body)
        body = {
            "iid": 9,
            "title": request.body["title"],
            "description": request.body["description"],
            "labels": ["type::testcase"],
            "web_url": "https://gitlab.test/nees/app/-/issues/9",
            "state": "opened",
        }
        return GatewayResponse(201, {}, json.dumps(body).encode())

    put = post


@pytest.fixture(autouse=True)
def token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-fake-0123456789abcdef")


async def _until(pilot, condition, tries: int = 100) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def test_g_asks_for_approval_and_then_pushes_the_case(tmp_path, monkeypatch) -> None:
    project = ProjectRepository(tmp_path).create(
        "Demo", repository="https://gitlab.test/nees/app"
    )
    repository = repository_for(tmp_path, project)
    save_settings(repository.root, SecuritySettings(allowed_hosts=("gitlab.test",)))
    create_test_case(
        repository,
        TestCaseDraft(
            title="Pagar",
            objective="Validar",
            steps=[Step("Pagar", "Pago")],
            expected_result="Pago",
        ),
    )
    gateway = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: gateway)

    async def push(app, pilot) -> None:
        await pilot.press("g")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        app.screen.query_one("#field-by", Input).value = "Ana"
        app.screen.query_one("#submit", Button).press()

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate("test-cases")
            await pilot.pause()

            await push(app, pilot)
            await _until(
                pilot, lambda: any("APR-" in n.message for n in app._notifications)
            )
            assert gateway.writes == []

            request_id = next(
                n.message for n in app._notifications if "APR-" in n.message
            )
            request_id = "APR-" + request_id.split("APR-")[1].split()[0].strip(".")
            from qa_workbench.security.audit import AuditLog
            from qa_workbench.security.guard import ActionGuard

            ActionGuard(
                SecuritySettings(allowed_hosts=("gitlab.test",)),
                AuditLog(repository.root),
            ).book.decide(request_id, approve=True, by="Bea")

            await push(app, pilot)
            await _until(pilot, lambda: gateway.writes)
            await _until(
                pilot, lambda: repository.get("TC-001").metadata.get("gitlab_iid")
            )
            assert repository.get("TC-001").metadata["gitlab_iid"] == 9
            assert gateway.writes[0]["issue_type"] == "test_case"

    asyncio.run(runner())
