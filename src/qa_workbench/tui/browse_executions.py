"""Rows and detail text for executions (pure, no widgets)."""

from qa_workbench.executions.states import State, next_states, parse_state
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.tui.browse import BrowseData, BrowseRow, as_list, section
from qa_workbench.tui.data import duration_text, effective_status
from qa_workbench.tui.status import Status, style_for

EXECUTION_COLUMNS = ("ID", "State", "Type", "Executor", "Case")
_MARKS = {"passed": "[x]", "failed": "[!]", "blocked": "[-]", "skipped": "[~]"}


def _case(repository: MarkdownRepository, case_id: str) -> str:
    if not case_id:
        return "-"
    try:
        title = repository.get(case_id).metadata.get("title", "")
        return f"{case_id} {title}".strip()
    except StorageError:
        return f"{case_id} (record not found)"


def _shown(state: str) -> str:
    """Symbol plus the state's own name (a symbol alone never carries the meaning)."""
    try:
        status = Status(state)
    except ValueError:
        status = Status.PENDING  # created, planned, awaiting_approval
    return f"{style_for(status).symbol} {state.replace('_', ' ').upper()}"


def execution_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("EXEC")
    rows = []
    ordered = sorted(
        listing.records,
        key=lambda r: r.metadata.get("updated_at") or r.metadata.get("created_at"),
        reverse=True,
    )
    for record in ordered:
        meta = record.metadata
        state = effective_status(meta)
        case = _case(repository, str(meta.get("test_case", "")))
        cells = (
            record.id,
            _shown(state),
            str(meta["execution_type"]),
            str(meta["executor"]),
            case,
        )
        rows.append(
            BrowseRow(
                record.id,
                cells,
                state,
                f"{record.id} {state} {meta['execution_type']} {meta['executor']} "
                f"{case} {meta.get('environment', '')}".lower(),
            )
        )
    return BrowseData(tuple(rows), tuple(f"EXEC: {e}" for e in listing.errors))


def allowed_moves(repository: MarkdownRepository, execution_id: str) -> list[str]:
    """The states this execution can move to now (empty when it is final)."""
    status = parse_state(repository.get(execution_id).metadata["status"])
    return sorted(state.value for state in next_states(status))


def execution_detail(repository: MarkdownRepository, execution_id: str) -> str:
    record = repository.get(execution_id)
    meta = record.metadata
    state = effective_status(meta)
    started, finished = meta.get("started_at"), meta.get("finished_at")
    lines = [
        f"{record.id}  {_shown(state)}",
        f"{_case(repository, str(meta.get('test_case', '')))}",
        f"Type {meta['execution_type']}   Executor {meta['executor']}   "
        f"Environment {meta['environment']}   Version {meta.get('version') or '-'}",
        f"Plan {meta.get('plan') or '-'}   Suite {meta.get('suite') or '-'}   "
        f"Duration {duration_text(started, finished)}",
    ]
    steps = [s for s in as_steps(meta) if isinstance(s, dict)]
    lines += ["", "STEPS"]
    for step in steps:
        outcome = step.get("outcome")
        mark = _MARKS.get(str(outcome), "[>]" if outcome is None else "[?]")
        observed = f"  ->  {step['observed']}" if step.get("observed") else ""
        lines.append(f"  {mark} {step.get('number')}. {step.get('action')}{observed}")
    if not steps:
        lines.append("  (no steps recorded yet)")
    if meta.get("observed_result"):
        lines += ["", "OBSERVED RESULT", f"  {meta['observed_result']}"]
    if meta.get("failure_type"):
        lines.append(f"  Failure type: {meta['failure_type']}")
    lines += section("EVIDENCE", as_list(meta.get("evidence")), "none attached")
    if meta.get("bugs"):
        lines += section("DEFECTS", as_list(meta["bugs"]))
    moves = allowed_moves(repository, execution_id)
    lines += [
        "",
        "NEXT: " + (", ".join(moves) if moves else "final, nothing can change it"),
    ]
    if State.RUNNING.value == meta["status"]:
        lines.append(
            "Record steps with `batman executions` (before and after each one)."
        )
    return "\n".join(lines)


def as_steps(meta: dict) -> list:
    steps = meta.get("steps_executed")
    return steps if isinstance(steps, list) else []
