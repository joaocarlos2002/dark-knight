"""GitLab pipelines, jobs, logs, and artifacts (read-only)."""

import re
from typing import Any
from urllib.parse import quote

from qa_workbench.integrations.errors import UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient
from qa_workbench.integrations.models import (
    ArtifactFile,
    Job,
    Pipeline,
    state_from_gitlab,
)

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")


def _seconds(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def pipeline_from(data: Any, endpoint: str) -> Pipeline:
    try:
        raw = str(data["status"])
        return Pipeline(
            id=int(data["id"]),
            state=state_from_gitlab(raw),
            raw_status=raw,
            ref=str(data.get("ref", "")),
            sha=str(data.get("sha", "")),
            source=str(data.get("source", "")),
            created_at=str(data.get("created_at", "")),
            duration_seconds=_seconds(data.get("duration")),
            url=str(data.get("web_url", "")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a pipeline is missing {error}", endpoint=endpoint
        ) from error


def job_from(data: Any, endpoint: str) -> Job:
    try:
        raw = str(data["status"])
        artifacts = tuple(
            ArtifactFile(
                str(item["filename"]),
                int(item.get("size") or 0),
                str(item.get("file_type", "")),
            )
            for item in data.get("artifacts") or []
        )
        return Job(
            id=int(data["id"]),
            name=str(data["name"]),
            stage=str(data.get("stage", "")),
            state=state_from_gitlab(raw),
            raw_status=raw,
            duration_seconds=_seconds(data.get("duration")),
            allow_failure=bool(data.get("allow_failure", False)),
            url=str(data.get("web_url", "")),
            failure_reason=str(data.get("failure_reason") or ""),
            artifacts=artifacts,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a job is missing {error}", endpoint=endpoint
        ) from error


class GitLabPipelines:
    """Implements :class:`PipelineSource` for GitLab.

    It only reads. Fetching a pipeline says what the server reports; it does
    not mean the tests passed: use :attr:`Pipeline.passed` and look at the jobs.
    """

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    def list_pipelines(
        self, *, ref: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[Pipeline]:
        path = self._client.project_path("/pipelines")
        params = {"order_by": "id", "sort": "desc"}
        if ref:
            params["ref"] = ref
        if status:
            params["status"] = status
        return [
            pipeline_from(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]

    def get_pipeline(self, pipeline_id: int) -> Pipeline:
        path = self._client.project_path(f"/pipelines/{pipeline_id}")
        return pipeline_from(self._client.get_json(path), path)

    def list_jobs(self, pipeline_id: int) -> list[Job]:
        path = self._client.project_path(f"/pipelines/{pipeline_id}/jobs")
        return [
            job_from(item, path)
            for item in self._client.get_list(
                path, {"include_retried": "true"}, limit=500
            )
        ]

    def job_log(self, job_id: int, *, max_chars: int = 20000) -> str:
        """The end of the job log (where failures are), without terminal codes."""
        path = self._client.project_path(f"/jobs/{job_id}/trace")
        raw = self._client.get_bytes(path, max_bytes=50_000_000)
        text = _ANSI.sub("", raw.decode("utf-8", errors="replace"))
        if len(text) > max_chars:
            return (
                f"[... {len(text) - max_chars} earlier characters omitted ...]\n"
                + text[-max_chars:]
            )
        return text

    def list_artifacts(self, job_id: int) -> list[ArtifactFile]:
        path = self._client.project_path(f"/jobs/{job_id}")
        return list(job_from(self._client.get_json(path), path).artifacts)

    def download_artifact(
        self, job_id: int, path: str, *, max_bytes: int = 10_000_000
    ) -> bytes:
        """One file from a job's artifacts. ``path`` is inside the archive."""
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError(
                f"Artifact path {path!r} must be relative and stay inside."
            )
        endpoint = self._client.project_path(
            f"/jobs/{job_id}/artifacts/{quote(path, safe='/')}"
        )
        return self._client.get_bytes(endpoint, max_bytes=max_bytes)
