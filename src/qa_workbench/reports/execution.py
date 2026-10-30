"""Execution report in Markdown (REQ-032, specification 11.1).

The report states facts taken from the records and nothing else: no result is
inferred, no evidence is assumed, and anything that limits how far the report
can be trusted is listed under *Limitations*. Sections follow the specification:
identification, objective, environment, preconditions, procedure, expected
result, observed result, status, evidence, and conclusion.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

from qa_workbench.reports.traceability import build_graph, trace
from qa_workbench.storage.errors import StorageError
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.history import history_path, sha256_file
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.tui.status import Status, format_status

_STATUS = {
    "passed": Status.PASSED,
    "failed": Status.FAILED,
    "blocked": Status.BLOCKED,
    "inconclusive": Status.INCONCLUSIVE,
    "cancelled": Status.CANCELLED,
    "running": Status.RUNNING,
}
_LABELS = {
    "product": "a product failure",
    "test": "a failure of the test itself",
    "infrastructure": "an infrastructure failure, which says nothing about the product",
    "evidence_collection": "a failure to collect evidence",
}


def _shown(status: str) -> str:
    return format_status(_STATUS.get(status, Status.PENDING)) + (
        "" if status in _STATUS else f" ({status})"
    )


def _effective(metadata: Mapping[str, Any]) -> str:
    status = str(metadata["status"])
    return str(metadata.get("result")) if status == "finalized" else status


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip() or 'Not recorded.'}"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _identification(record: Record, case: Record | None) -> str:
    metadata = record.metadata
    rows = [
        f"Execution: {record.id}",
        f"Type: {str(metadata['execution_type']).replace('_', ' ')}",
        f"Executor: {metadata['executor']}",
    ]
    if case is not None:
        rows.append(f"Test case: [[{case.id}]] {case.metadata['title']}")
    for key, label in (("plan", "Plan"), ("suite", "Suite"), ("project", "Project")):
        if metadata.get(key):
            rows.append(f"{label}: [[{metadata[key]}]]")
    if metadata.get("automation_tool"):
        rows.append(f"Automation tool: {metadata['automation_tool']}")
    return _bullets(rows)


def _environment(metadata: Mapping[str, Any]) -> str:
    rows = [f"Environment: {metadata['environment']}"]
    for key, label in (
        ("version", "Version"),
        ("branch", "Branch"),
        ("commit", "Commit"),
    ):
        if metadata.get(key):
            rows.append(f"{label}: {metadata[key]}")
    return _bullets(rows)


def _preconditions(metadata: Mapping[str, Any], case: Record | None) -> str:
    checked = {
        item["text"]: item["checked"]
        for item in metadata.get("preconditions_checked") or []
        if isinstance(item, dict)
    }
    rows = [f"{'Met' if ok else 'NOT met'}: {text}" for text, ok in checked.items()]
    if case is not None:
        declared = [
            p for p in case.metadata.get("preconditions") or [] if p not in checked
        ]
        rows += [f"Not verified: {text}" for text in declared]
    return _bullets(rows)


def _procedure(metadata: Mapping[str, Any], case: Record | None) -> str:
    steps = metadata.get("steps_executed") or []
    if steps:
        lines = []
        for step in steps:
            outcome = step.get("outcome") or "in progress"
            line = f"{step['number']}. {step['action']} - {outcome}"
            if step.get("observed"):
                line += f" ({step['observed']})"
            lines.append(line)
        return "\n".join(lines)
    if case is not None and case.metadata.get("steps"):
        planned = "\n".join(
            f"{n}. {s['action']}" for n, s in enumerate(case.metadata["steps"], start=1)
        )
        return f"Steps were not recorded one by one. The case defines:\n\n{planned}"
    return ""


def _evidence(
    repository: MarkdownRepository, metadata: Mapping[str, Any]
) -> tuple[str, list[str]]:
    ids = list(metadata.get("evidence") or [])
    limitations: list[str] = []
    if not ids:
        return "No evidence was collected.", limitations
    store = EvidenceStore(repository) if "EVD" in repository.prefixes else None
    lines: list[str] = []
    for evidence_id in ids:
        if store is None:
            lines.append(f"[[{evidence_id}]] (evidence records are not available)")
            continue
        try:
            record = store.get(evidence_id)
        except StorageError as error:
            lines.append(f"[[{evidence_id}]] could not be read: {error}")
            limitations.append(f"{evidence_id} could not be read.")
            continue
        meta = record.metadata
        problems = store.verify(evidence_id)
        integrity = "integrity verified" if not problems else "INTEGRITY PROBLEM"
        lines.append(
            f"[[{evidence_id}]] {meta['description']} - {meta['source']}, "
            f"sha256 {str(meta['sha256'])[:12]}, {meta['size']} bytes, {integrity}"
        )
        limitations += [f"{evidence_id}: {problem}" for problem in problems]
    return _bullets(lines), limitations


def _traceability(repository: MarkdownRepository, record: Record) -> str:
    chain = trace(build_graph(repository), record.id)
    rows = [
        f"Upstream {kind}: {', '.join(f'[[{i}]]' for i in ids)}"
        for kind, ids in chain.upstream.items()
    ]
    rows += [
        f"Downstream {kind}: {', '.join(f'[[{i}]]' for i in ids)}"
        for kind, ids in chain.downstream.items()
    ]
    bugs = record.metadata.get("bugs") or []
    if bugs and "BUG" not in repository.prefixes:
        rows.append(
            f"Defects: {', '.join(bugs)} (referenced; defect records are not "
            "stored yet)"
        )
    return _bullets(rows)


def _limitations(
    repository: MarkdownRepository,
    record: Record,
    evidence_limitations: list[str],
) -> list[str]:
    metadata = record.metadata
    status = str(metadata["status"])
    effective = _effective(metadata)
    found = list(evidence_limitations)
    if status != "finalized":
        found.append(
            f"The execution is {status}, not finalized; this report may change."
        )
    if effective in {"passed", "failed"} and not metadata.get("evidence"):
        found.append("No evidence was collected.")
    if effective in {
        "passed",
        "failed",
        "blocked",
        "inconclusive",
    } and not metadata.get("steps_executed"):
        found.append("The steps were not recorded one by one.")
    interrupted = [
        str(step["number"])
        for step in metadata.get("steps_executed") or []
        if step.get("outcome") == "interrupted"
    ]
    if interrupted:
        found.append(
            f"Step(s) {', '.join(interrupted)} were interrupted and not observed."
        )
    for entry in metadata.get("recoveries") or []:
        found.append(
            f"Recovered after an interruption ({entry['action']}): {entry['note']}"
        )
    if metadata.get("failure_type"):
        found.append(
            f"The failure was classified as {_LABELS[metadata['failure_type']]}."
        )
    if status == "finalized":
        events = [e for e in repository.history(record.id) if e.kind != "sealed"]
        for event in events:
            found.append(
                f"{event.kind.capitalize()} recorded by {event.author}: "
                f"{event.justification}"
            )
        problems = repository.verify(record.id)
        found += [f"Integrity: {problem}" for problem in problems]
    return found


def _conclusion(metadata: Mapping[str, Any]) -> str:
    effective = _effective(metadata)
    evidence = metadata.get("evidence") or []
    if effective == "passed":
        return f"The execution passed, with {len(evidence)} evidence item(s) recorded."
    if effective == "failed":
        return f"The execution failed. Observed: {metadata.get('observed_result')}"
    if effective in {"blocked", "inconclusive", "cancelled"}:
        return f"The execution is {effective}. Reason: {metadata.get('reason')}"
    return f"No conclusion yet: the execution is {metadata['status']}."


def render_execution_report(repository: MarkdownRepository, execution_id: str) -> str:
    """Build the report of one execution as Markdown."""
    record = repository.get(execution_id)
    metadata = record.metadata
    case: Record | None = None
    case_id = metadata.get("test_case")
    if case_id and "TC" in repository.prefixes:
        try:
            case = repository.get(case_id)
        except StorageError:
            case = None

    evidence_text, evidence_limitations = _evidence(repository, metadata)
    limitations = _limitations(repository, record, evidence_limitations)
    effective = _effective(metadata)
    objective = (
        str(case.metadata["objective"])
        if case is not None
        else "No test case is linked (exploratory session)."
    )
    timing = ""
    if metadata.get("started_at"):
        timing = f"Started: {metadata['started_at'].isoformat()}"
        if metadata.get("finished_at"):
            timing += f"\nFinished: {metadata['finished_at'].isoformat()}"
        if metadata.get("duration_seconds") is not None:
            timing += f"\nDuration: {metadata['duration_seconds']} s"
    parts = [
        f"# Execution report {record.id}",
        _section("Identification", _identification(record, case)),
        _section("Objective", objective),
        _section("Environment", _environment(metadata)),
        _section("Preconditions", _preconditions(metadata, case)),
        _section("Procedure", _procedure(metadata, case)),
        _section("Expected result", str(metadata.get("expected_result") or "")),
        _section("Observed result", str(metadata.get("observed_result") or "")),
        _section("Status", f"{_shown(effective)}\n\n{timing}"),
        _section("Evidence", evidence_text),
        _section("Conclusion", _conclusion(metadata)),
        _section(
            "Limitations",
            _bullets(limitations) if limitations else "None known.",
        ),
        _section("Traceability", _traceability(repository, record)),
    ]
    return "\n\n".join(parts) + "\n"


def source_hash(repository: MarkdownRepository, execution_id: str) -> str:
    """SHA-256 of the execution and its history, to tell whether a report is stale.

    Corrections live in the history file, so it is part of what the report
    describes.
    """
    path = repository.path_of(execution_id)
    digest = hashlib.sha256(sha256_file(path).encode())
    history = history_path(path)
    if history.is_file():
        digest.update(sha256_file(history).encode())
    return digest.hexdigest()
