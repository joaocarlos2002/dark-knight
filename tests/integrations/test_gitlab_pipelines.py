import pytest
from fake_gitlab import PREFIX, FakeGateway, answer, make_client

from qa_workbench.integrations.errors import NotFoundError, UnexpectedResponseError
from qa_workbench.integrations.gitlab.pipelines import GitLabPipelines
from qa_workbench.integrations.models import PipelineState, state_from_gitlab

PIPELINE = {
    "id": 100,
    "status": "failed",
    "ref": "main",
    "sha": "abc123",
    "source": "push",
    "created_at": "2026-10-03T08:00:00Z",
    "duration": 125,
    "web_url": "https://gitlab.test/group/app/-/pipelines/100",
}
JOB = {
    "id": 900,
    "name": "unit-tests",
    "stage": "test",
    "status": "failed",
    "duration": 41.5,
    "allow_failure": False,
    "failure_reason": "script_failure",
    "web_url": "https://gitlab.test/group/app/-/jobs/900",
    "artifacts": [{"filename": "report.xml", "size": 120, "file_type": "junit"}],
}


def _pipelines(routes):
    gateway = FakeGateway({PREFIX + k: v for k, v in routes.items()})
    return GitLabPipelines(make_client(gateway)), gateway


def test_lists_pipelines_for_a_ref_and_status() -> None:
    pipelines, gateway = _pipelines({"/pipelines": [PIPELINE]})

    found = pipelines.list_pipelines(ref="main", status="failed", limit=5)

    assert found[0].id == 100 and found[0].state is PipelineState.FAILED
    assert found[0].duration_seconds == 125 and found[0].finished
    assert gateway.requests[0].params["ref"] == "main"
    assert gateway.requests[0].params["status"] == "failed"


def test_only_a_success_status_counts_as_passed() -> None:
    pipelines, _ = _pipelines(
        {"/pipelines/1": {**PIPELINE, "id": 1, "status": "success"}}
    )

    ok = pipelines.get_pipeline(1)

    assert ok.passed and ok.finished
    for raw in ("created", "pending", "running", "manual", "skipped", "canceled"):
        state = state_from_gitlab(raw)
        assert state is not PipelineState.SUCCESS


def test_a_created_pipeline_is_not_finished_or_passed() -> None:
    pipelines, _ = _pipelines(
        {"/pipelines/2": {**PIPELINE, "id": 2, "status": "created", "duration": None}}
    )

    created = pipelines.get_pipeline(2)

    assert not created.finished and not created.passed
    assert created.duration_seconds is None


def test_state_mapping_covers_the_specification_and_keeps_unknowns() -> None:
    assert state_from_gitlab("waiting_for_resource") is PipelineState.BLOCKED
    assert state_from_gitlab("preparing") is PipelineState.PENDING
    unknown = state_from_gitlab("brand_new_status")
    assert unknown is PipelineState.UNKNOWN


def test_unknown_status_keeps_the_raw_value() -> None:
    pipelines, _ = _pipelines(
        {"/pipelines/3": {**PIPELINE, "id": 3, "status": "brand_new_status"}}
    )

    pipeline = pipelines.get_pipeline(3)

    assert pipeline.state is PipelineState.UNKNOWN
    assert pipeline.raw_status == "brand_new_status" and not pipeline.passed


def test_jobs_carry_stage_failure_reason_and_artifacts() -> None:
    pipelines, gateway = _pipelines({"/pipelines/100/jobs": [JOB]})

    job = pipelines.list_jobs(100)[0]

    assert (job.name, job.stage, job.failure_reason) == (
        "unit-tests",
        "test",
        "script_failure",
    )
    assert job.artifacts[0].filename == "report.xml" and job.artifacts[0].size == 120
    assert gateway.requests[0].params["include_retried"] == "true"


def test_log_is_cleaned_and_trimmed_to_the_end() -> None:
    trace = b"\x1b[0Ksection\x1b[31;1mERROR\x1b[0m " + b"x" * 100 + b" the end"
    pipelines, _ = _pipelines({"/jobs/900/trace": lambda r: answer(trace)})

    log = pipelines.job_log(900, max_chars=20)

    assert "\x1b" not in log and log.endswith("the end")
    assert "earlier characters omitted" in log
    assert "ERROR" in pipelines.job_log(900, max_chars=10_000)


def test_missing_log_is_not_an_empty_log() -> None:
    pipelines, _ = _pipelines({})

    with pytest.raises(NotFoundError):
        pipelines.job_log(404)


def test_artifacts_are_listed_from_the_job() -> None:
    pipelines, _ = _pipelines({"/jobs/900": JOB})

    assert [a.filename for a in pipelines.list_artifacts(900)] == ["report.xml"]


def test_artifact_download_returns_the_bytes_within_the_limit() -> None:
    pipelines, gateway = _pipelines(
        {"/jobs/900/artifacts/reports/junit.xml": lambda r: answer(b"<xml/>")}
    )

    assert pipelines.download_artifact(900, "reports/junit.xml") == b"<xml/>"
    with pytest.raises(UnexpectedResponseError, match="limit"):
        pipelines.download_artifact(900, "reports/junit.xml", max_bytes=2)
    assert gateway.requests[0].url.endswith("/artifacts/reports/junit.xml")


@pytest.mark.parametrize("bad", ["", "/etc/passwd", "../secret", "a/../../b"])
def test_artifact_paths_cannot_escape(bad: str) -> None:
    pipelines, gateway = _pipelines({})

    with pytest.raises(ValueError, match="relative"):
        pipelines.download_artifact(900, bad)
    assert gateway.requests == []


def test_malformed_pipeline_and_job_are_reported() -> None:
    pipelines, _ = _pipelines(
        {"/pipelines": [{"id": 1}], "/pipelines/1/jobs": [{"id": 1}]}
    )

    with pytest.raises(UnexpectedResponseError, match="pipeline is missing"):
        pipelines.list_pipelines()
    with pytest.raises(UnexpectedResponseError, match="job is missing"):
        pipelines.list_jobs(1)
