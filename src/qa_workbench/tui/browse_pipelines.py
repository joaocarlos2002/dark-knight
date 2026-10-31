"""Rows and detail text for CI pipelines read from GitLab (pure, no widgets)."""

from collections import defaultdict

from qa_workbench.integrations.models import Job, Pipeline, PipelineState
from qa_workbench.tui.status import Status, style_for

PIPELINE_COLUMNS = ("ID", "State", "Ref", "Commit", "Time")

_STATUS = {
    PipelineState.SUCCESS: Status.PASSED,
    PipelineState.FAILED: Status.FAILED,
    PipelineState.RUNNING: Status.RUNNING,
    PipelineState.CANCELED: Status.CANCELLED,
    PipelineState.SKIPPED: Status.SKIPPED,
    PipelineState.BLOCKED: Status.BLOCKED,
}


def state_text(state: PipelineState, raw: str) -> str:
    """Symbol plus the state's own name (the server's word when it is unknown)."""
    status = _STATUS.get(state, Status.PENDING)
    name = (
        raw.upper().replace("_", " ")
        if state is PipelineState.UNKNOWN
        else state.value.upper()
    )
    return f"{style_for(status).symbol} {name}"


def _seconds(value: float | None) -> str:
    if value is None:
        return "-"
    minutes, seconds = divmod(int(value), 60)
    return f"{minutes:02d}:{seconds:02d}"


def pipeline_cells(pipeline: Pipeline) -> tuple[str, ...]:
    return (
        str(pipeline.id),
        state_text(pipeline.state, pipeline.raw_status),
        pipeline.ref or "-",
        pipeline.sha[:8] or "-",
        _seconds(pipeline.duration_seconds),
    )


def pipeline_detail(pipeline: Pipeline, jobs: list[Job] | None) -> str:
    """The pipeline and, by stage, its jobs. ``jobs=None`` means not loaded yet."""
    lines = [
        f"Pipeline {pipeline.id}  {state_text(pipeline.state, pipeline.raw_status)}",
        f"Ref {pipeline.ref or '-'}   Commit {pipeline.sha[:12] or '-'}   "
        f"Source {pipeline.source or '-'}   Time {_seconds(pipeline.duration_seconds)}",
        pipeline.url,
        "",
    ]
    if pipeline.passed:
        lines.append(
            "GitLab reports success. That is the server's word, not a test result."
        )
    elif not pipeline.finished:
        lines.append("Not finished: nothing can be concluded about it yet.")
    if jobs is None:
        return "\n".join([*lines, "", "Loading jobs..."])
    stages: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        stages[job.stage or "(no stage)"].append(job)
    lines += ["", "STAGES"]
    for stage, stage_jobs in stages.items():
        lines.append(f"  {stage}")
        for job in stage_jobs:
            reason = f"  {job.failure_reason}" if job.failure_reason else ""
            soft = ""
            if job.allow_failure and job.state is not PipelineState.SUCCESS:
                soft = "  (allowed to fail)"
            lines.append(
                f"    {state_text(job.state, job.raw_status):<14} {job.name}  "
                f"{_seconds(job.duration_seconds)}  job {job.id}{reason}{soft}"
            )
    if not jobs:
        lines.append("  (no jobs)")
    failed = [
        j for j in jobs if j.state is PipelineState.FAILED and not j.allow_failure
    ]
    if failed:
        lines += [
            "",
            "FAILED JOBS: " + ", ".join(f"{j.name} (job {j.id})" for j in failed),
        ]
        lines.append("Read a log with `batman gitlab log JOB -p PROJ`.")
    return "\n".join(lines)
