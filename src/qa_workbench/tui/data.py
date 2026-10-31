"""What the pages show, read from the project's records (no widgets here).

Every number comes from persisted records. A damaged record is counted and
reported next to the valid ones, never dropped, and a value that cannot be
computed is ``None`` (shown as ``n/a``), never zero.
"""

from dataclasses import dataclass, field
from datetime import datetime

from qa_workbench.projects.models import Project
from qa_workbench.projects.repository import ProjectListing
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.tui.status import Status

RESULT_ORDER = ("passed", "failed", "blocked", "inconclusive", "cancelled")
IN_PROGRESS = frozenset(
    {"created", "planned", "awaiting_approval", "running"},
)
RECENT_LIMIT = 8


@dataclass(frozen=True)
class ProjectRow:
    id: str
    name: str
    status: str
    repository: str
    environments: str


def project_rows(listing: ProjectListing) -> list[ProjectRow]:
    return [
        ProjectRow(
            p.id,
            p.name,
            p.status.value,
            p.repository or "-",
            ", ".join(e.name for e in p.environments) or "-",
        )
        for p in listing.projects
    ]


@dataclass(frozen=True)
class RecentExecution:
    id: str
    case: str
    status: Status | None
    status_text: str
    duration: str


@dataclass(frozen=True)
class OverviewData:
    project: Project
    test_cases: int | None
    requirements: int | None
    results: dict[str, int]
    in_progress: int
    recent: tuple[RecentExecution, ...]
    problems: tuple[str, ...] = field(default_factory=tuple)


def effective_status(metadata: dict) -> str:
    """The result of a finalized execution, otherwise its state."""
    status = str(metadata.get("status", ""))
    if status == "finalized":
        return str(metadata.get("result") or "finalized")
    return status


def duration_text(started: object, finished: object) -> str:
    if not isinstance(started, datetime) or not isinstance(finished, datetime):
        return "-"
    seconds = max(0, int((finished - started).total_seconds()))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _status_of(name: str) -> Status | None:
    try:
        return Status(name)
    except ValueError:
        return {"running": Status.RUNNING, "created": Status.PENDING}.get(name)


def _count(
    repository: MarkdownRepository, prefix: str, problems: list[str]
) -> int | None:
    if prefix not in repository.prefixes:
        return None
    listing = repository.list_records(prefix)
    problems.extend(f"{prefix}: {error}" for error in listing.errors)
    return len(listing.records)


def _case_title(repository: MarkdownRepository, case_id: str) -> str:
    if not case_id:
        return "-"
    try:
        return f"{case_id} {repository.get(case_id).metadata.get('title', '')}".strip()
    except StorageError:
        return f"{case_id} (record not found)"


def _sort_key(record: Record) -> str:
    stamp = record.metadata.get("updated_at") or record.metadata.get("created_at")
    return stamp.isoformat() if isinstance(stamp, datetime) else ""


def build_overview(repository: MarkdownRepository, project: Project) -> OverviewData:
    problems: list[str] = []
    cases = _count(repository, "TC", problems)
    requirements = _count(repository, "REQ", problems)
    results = dict.fromkeys(RESULT_ORDER, 0)
    in_progress = 0
    recent: list[RecentExecution] = []
    if "EXEC" in repository.prefixes:
        listing = repository.list_records("EXEC")
        problems.extend(f"EXEC: {error}" for error in listing.errors)
        for record in listing.records:
            effective = effective_status(record.metadata)
            if effective in results:
                results[effective] += 1
            elif effective in IN_PROGRESS:
                in_progress += 1
        for record in sorted(listing.records, key=_sort_key, reverse=True)[
            :RECENT_LIMIT
        ]:
            effective = effective_status(record.metadata)
            recent.append(
                RecentExecution(
                    record.id,
                    _case_title(repository, str(record.metadata.get("test_case", ""))),
                    _status_of(effective),
                    effective,
                    duration_text(
                        record.metadata.get("started_at"),
                        record.metadata.get("finished_at"),
                    ),
                )
            )
    return OverviewData(
        project,
        cases,
        requirements,
        results,
        in_progress,
        tuple(recent),
        tuple(problems),
    )
