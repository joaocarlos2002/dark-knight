"""What the workbench needs from a tracker and a CI system.

GitLab implements these today; GitHub can implement them later without changes
to the code that uses them. Everything here is read-only: writing back to an
external system is a separate, approved action (REQ-027).
"""

from typing import Protocol

from qa_workbench.integrations.models import (
    ArtifactFile,
    Commit,
    Issue,
    Job,
    MergeRequest,
    Note,
    Pipeline,
)


class IssueSource(Protocol):
    def list_issues(
        self, *, state: str = "opened", labels: tuple[str, ...] = (), limit: int = 20
    ) -> list[Issue]: ...

    def get_issue(self, iid: int) -> Issue: ...

    def list_notes(self, iid: int, *, limit: int = 100) -> list[Note]: ...


class RepositorySource(Protocol):
    def list_commits(
        self, *, ref: str | None = None, since: str | None = None, limit: int = 20
    ) -> list[Commit]: ...

    def get_commit(self, sha: str) -> Commit: ...

    def list_merge_requests(
        self, *, state: str = "opened", limit: int = 20
    ) -> list[MergeRequest]: ...

    def get_merge_request(self, iid: int) -> MergeRequest: ...


class PipelineSource(Protocol):
    def list_pipelines(
        self, *, ref: str | None = None, status: str | None = None, limit: int = 20
    ) -> list[Pipeline]: ...

    def get_pipeline(self, pipeline_id: int) -> Pipeline: ...

    def list_jobs(self, pipeline_id: int) -> list[Job]: ...

    def job_log(self, job_id: int, *, max_chars: int = 20000) -> str: ...

    def list_artifacts(self, job_id: int) -> list[ArtifactFile]: ...

    def download_artifact(
        self, job_id: int, path: str, *, max_bytes: int = 10_000_000
    ) -> bytes: ...
