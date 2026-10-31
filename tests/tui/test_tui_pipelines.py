import asyncio
import json
from pathlib import Path

import pytest
from textual.widgets import DataTable as TextualDataTable
from textual.widgets import Static

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayError, GatewayRequest, GatewayResponse
from qa_workbench.integrations.models import Job, Pipeline, PipelineState
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.security.settings import SecuritySettings, save_settings
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.browse_pipelines import (
    pipeline_cells,
    pipeline_detail,
    state_text,
)
from qa_workbench.workspace import repository_for

URL = "https://gitlab.test/group/app"
P = "/api/v4/projects/group%2Fapp"
PIPELINES = [
    {"id": 18, "status": "running", "ref": "develop", "sha": "abcdef1234567890"},
    {
        "id": 17,
        "status": "failed",
        "ref": "develop",
        "sha": "1234567890abcdef",
        "duration": 105,
    },
    {"id": 16, "status": "weird_new_status", "ref": "main", "sha": "ffffffffffffffff"},
]
JOBS = {
    17: [
        {
            "id": 901,
            "name": "unit",
            "stage": "test",
            "status": "success",
            "duration": 12,
        },
        {
            "id": 902,
            "name": "functional",
            "stage": "e2e",
            "status": "failed",
            "duration": 42,
            "failure_reason": "script_failure",
        },
        {
            "id": 903,
            "name": "lint",
            "stage": "test",
            "status": "failed",
            "allow_failure": True,
        },
    ],
}


class Gateway:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.status = 200
        self.failure: GatewayError | None = None

    def get(self, request: GatewayRequest) -> GatewayResponse:
        self.requests.append(request.url)
        if self.failure:
            raise self.failure
        if self.status != 200:
            return GatewayResponse(self.status, {}, b'{"message": "x"}')
        path = request.url.removeprefix("https://gitlab.test")
        if path == P + "/pipelines":
            body = PIPELINES
        elif path.startswith(P + "/pipelines/") and path.endswith("/jobs"):
            body = JOBS.get(int(path.split("/")[-2]), [])
        else:
            return GatewayResponse(404, {}, b"{}")
        return GatewayResponse(200, {}, json.dumps(body).encode())


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Gateway:
    fake = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: fake)
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test-token-0123456789")
    return fake


@pytest.fixture
def project(tmp_path: Path):
    created = ProjectRepository(tmp_path).create("Demo", repository=URL)
    root = repository_for(tmp_path, created).root
    save_settings(root, SecuritySettings(allowed_hosts=("gitlab.test",)))
    return created


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


async def _until(pilot, condition, tries: int = 100) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _text(app, selector: str) -> str:
    page = app.query_one("#page-pipelines")
    return str(page.query_one(selector, Static).render())


def _keys(app) -> list[str]:
    table = app.query_one("#page-pipelines #pipe-table").query_one(TextualDataTable)
    return [
        str(table.coordinate_to_cell_key((i, 0)).row_key.value)
        for i in range(table.row_count)
    ]


def _pipeline(**fields) -> Pipeline:
    values = {
        "id": 1,
        "state": PipelineState.FAILED,
        "raw_status": "failed",
        "ref": "main",
        "sha": "abcdef1234567890",
        "source": "push",
        "created_at": "",
        "duration_seconds": 65.0,
        "url": "https://gitlab.test/p/1",
    }
    return Pipeline(**{**values, **fields})


# -- view-models ----------------------------------------------------------------------


def test_cells_show_symbol_and_name_and_keep_unknown_statuses() -> None:
    assert pipeline_cells(_pipeline()) == ("1", "✗ FAILED", "main", "abcdef12", "01:05")
    unknown = _pipeline(
        state=PipelineState.UNKNOWN, raw_status="brand_new", duration_seconds=None
    )
    assert pipeline_cells(unknown)[1] == "◷ BRAND NEW"
    assert pipeline_cells(unknown)[4] == "-"
    assert state_text(PipelineState.SUCCESS, "success") == "✓ SUCCESS"


def test_detail_groups_jobs_by_stage_and_names_failures() -> None:
    jobs = [
        Job(1, "unit", "test", PipelineState.SUCCESS, "success", 12.0, False, "u"),
        Job(
            2,
            "e2e",
            "e2e",
            PipelineState.FAILED,
            "failed",
            42.0,
            False,
            "u",
            "script_failure",
        ),
        Job(3, "lint", "test", PipelineState.FAILED, "failed", None, True, "u"),
    ]

    text = pipeline_detail(_pipeline(), jobs)

    assert "STAGES\n  test\n" in text and "script_failure" in text
    assert "(allowed to fail)" in text
    failed_line = next(line for line in text.splitlines() if "FAILED JOBS" in line)
    assert "e2e (job 2)" in failed_line and "lint" not in failed_line
    assert "Loading jobs..." in pipeline_detail(_pipeline(), None)
    assert "(no jobs)" in pipeline_detail(_pipeline(), [])


def test_success_is_the_servers_word_and_unfinished_proves_nothing() -> None:
    done = _pipeline(state=PipelineState.SUCCESS, raw_status="success")
    running = _pipeline(state=PipelineState.RUNNING, raw_status="running")

    assert "not a test result" in pipeline_detail(done, [])
    assert "nothing can be concluded" in pipeline_detail(running, [])


# -- the page --------------------------------------------------------------------------


def test_nothing_is_fetched_until_asked(tmp_path, project, gateway) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        assert "press R" in _text(app, "#pipe-summary")
        assert gateway.requests == []

    _run(tmp_path, scenario, project)


def test_without_a_project_it_says_so(tmp_path, gateway) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        assert "No project is open" in _text(app, "#pipe-summary")

    _run(tmp_path, scenario)


def test_fetching_lists_pipelines_and_selecting_loads_its_jobs(
    tmp_path, project, gateway
) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        await pilot.press("r")
        await _until(pilot, lambda: _keys(app) == ["18", "17", "16"])
        assert "3 pipeline(s) from https://gitlab.test" in _text(app, "#pipe-summary")

        await pilot.press("down")  # pipeline 17 has jobs
        await _until(
            pilot,
            lambda: "FAILED JOBS: functional (job 902)" in _text(app, "#pipe-detail"),
        )
        detail = _text(app, "#pipe-detail")
        assert "script_failure" in detail and "(allowed to fail)" in detail

    _run(tmp_path, scenario, project)


def test_failures_are_explicit_never_an_empty_list(tmp_path, project, gateway) -> None:
    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        gateway.status = 401
        await pilot.press("r")
        await _until(pilot, lambda: "token was rejected" in _text(app, "#pipe-summary"))
        assert "HTTP 401" in _text(app, "#pipe-summary") and _keys(app) == []

        gateway.status, gateway.failure = 200, GatewayError("connection refused")
        await pilot.press("r")
        await _until(pilot, lambda: "reachable" in _text(app, "#pipe-summary"))

    _run(tmp_path, scenario, project)


def test_a_missing_token_stops_before_any_request(
    tmp_path, project, gateway, monkeypatch
) -> None:
    monkeypatch.delenv("GITLAB_TOKEN")

    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        await pilot.press("r")
        await _until(
            pilot, lambda: "GITLAB_TOKEN is not set" in _text(app, "#pipe-summary")
        )
        assert gateway.requests == []

    _run(tmp_path, scenario, project)


def test_a_host_outside_the_scope_asks_for_approval(tmp_path, gateway) -> None:
    created = ProjectRepository(tmp_path).create("Demo", repository=URL)

    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        await pilot.press("r")
        await _until(pilot, lambda: "needs approval" in _text(app, "#pipe-summary"))
        assert "APR-" in _text(app, "#pipe-summary") and gateway.requests == []

    _run(tmp_path, scenario, created)


def test_a_project_without_a_repository_url_says_so(tmp_path, gateway) -> None:
    created = ProjectRepository(tmp_path).create("Demo")

    async def scenario(app, pilot) -> None:
        app.navigate("pipelines")
        await pilot.pause()
        await pilot.press("r")
        await _until(pilot, lambda: "no repository URL" in _text(app, "#pipe-summary"))

    _run(tmp_path, scenario, created)
