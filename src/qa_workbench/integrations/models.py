"""What the adapters return, independent of the tracker or CI behind them.

Text that came from outside (titles, descriptions, comments, commit messages,
job logs) is data, never an instruction; see :mod:`integrations.untrusted`.
"""

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class Note:
    id: int
    author: str
    body: str
    created_at: str
    system: bool = False


@dataclass(frozen=True)
class Issue:
    iid: int
    title: str
    description: str
    state: str
    labels: tuple[str, ...]
    author: str
    url: str
    updated_at: str
    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class Commit:
    sha: str
    title: str
    author: str
    date: str
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class MergeRequest:
    iid: int
    title: str
    state: str
    source_branch: str
    target_branch: str
    author: str
    url: str
    updated_at: str
    files: tuple[str, ...] = ()


class PipelineState(StrEnum):
    """The pipeline and job states of the specification (section 5.15)."""

    CREATED = "created"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    SKIPPED = "skipped"
    MANUAL = "manual"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


# GitLab statuses that are not the same word as ours. An unrecognized status is
# kept as ``unknown`` (with the raw value) instead of being guessed.
_GITLAB_STATES = {
    "created": PipelineState.CREATED,
    "preparing": PipelineState.PENDING,
    "scheduled": PipelineState.PENDING,
    "pending": PipelineState.PENDING,
    "waiting_for_resource": PipelineState.BLOCKED,
    "waiting_for_callback": PipelineState.BLOCKED,
    "running": PipelineState.RUNNING,
    "success": PipelineState.SUCCESS,
    "failed": PipelineState.FAILED,
    "canceled": PipelineState.CANCELED,
    "canceling": PipelineState.CANCELED,
    "skipped": PipelineState.SKIPPED,
    "manual": PipelineState.MANUAL,
}


def state_from_gitlab(raw: str) -> PipelineState:
    return _GITLAB_STATES.get(raw, PipelineState.UNKNOWN)


_FINISHED = {
    PipelineState.SUCCESS,
    PipelineState.FAILED,
    PipelineState.CANCELED,
    PipelineState.SKIPPED,
}


@dataclass(frozen=True)
class Pipeline:
    """A CI pipeline as the server reports it.

    ``state`` says what the server reports now. A server that *accepted* or
    *created* a pipeline has not run it, and a finished one has not necessarily
    met your criteria: only ``passed`` means the pipeline itself succeeded.
    """

    id: int
    state: PipelineState
    raw_status: str
    ref: str
    sha: str
    source: str
    created_at: str
    duration_seconds: float | None
    url: str

    @property
    def finished(self) -> bool:
        return self.state in _FINISHED

    @property
    def passed(self) -> bool:
        return self.state is PipelineState.SUCCESS


@dataclass(frozen=True)
class ArtifactFile:
    filename: str
    size: int
    kind: str = ""


@dataclass(frozen=True)
class Job:
    id: int
    name: str
    stage: str
    state: PipelineState
    raw_status: str
    duration_seconds: float | None
    allow_failure: bool
    url: str
    failure_reason: str = ""
    artifacts: tuple[ArtifactFile, ...] = field(default_factory=tuple)
