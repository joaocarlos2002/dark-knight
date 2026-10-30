"""Traceability across records (REQ-032).

Records form a chain, from what was asked to what was observed::

    requirement -> test case -> suite -> plan -> execution -> evidence / defect

A link can be written on either side (a requirement lists its cases, or a case
lists its requirements), so the graph takes the union. From any record,
``trace`` follows the chain upstream (towards the requirement) and downstream
(towards the evidence) without wandering sideways into unrelated records.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from qa_workbench.storage.ids import parse_id
from qa_workbench.storage.repository import MarkdownRepository, Record

# The chain, in order. A record only links to records of other kinds.
LAYERS = {"REQ": 0, "TC": 1, "SUITE": 2, "TP": 3, "EXEC": 4, "EVD": 5, "BUG": 5}
KINDS = ("REQ", "TC", "SUITE", "TP", "EXEC", "EVD", "BUG")


@dataclass(frozen=True)
class Link:
    lower: str
    upper: str
    relation: str


@dataclass
class TraceGraph:
    """Records and the links between them."""

    titles: dict[str, str] = field(default_factory=dict)
    links: set[Link] = field(default_factory=set)

    def exists(self, record_id: str) -> bool:
        return record_id in self.titles

    def neighbours(self, record_id: str) -> set[str]:
        found: set[str] = set()
        for link in self.links:
            if link.lower == record_id:
                found.add(link.upper)
            elif link.upper == record_id:
                found.add(link.lower)
        return found


@dataclass(frozen=True)
class Trace:
    """The records connected to one record, by kind."""

    record_id: str
    upstream: dict[str, tuple[str, ...]]
    downstream: dict[str, tuple[str, ...]]


def _prefix(record_id: str) -> str:
    return parse_id(record_id).prefix


def _ids(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _add(graph: TraceGraph, first: str, second: str, relation: str) -> None:
    try:
        one, two = _prefix(first), _prefix(second)
    except ValueError:
        return
    if LAYERS.get(one) is None or LAYERS.get(two) is None or one == two:
        return
    lower, upper = (first, second) if LAYERS[one] < LAYERS[two] else (second, first)
    graph.links.add(Link(lower, upper, relation))


def _label(record: Record) -> str:
    return str(record.metadata.get("title") or record.metadata.get("description") or "")


def build_graph(repository: MarkdownRepository) -> TraceGraph:
    """Read every record kind the repository stores and link them."""
    graph = TraceGraph()
    records: dict[str, list[Record]] = {}
    for prefix in KINDS:
        if prefix in repository.prefixes:
            records[prefix] = list(repository.list_records(prefix).records)
            for record in records[prefix]:
                graph.titles[record.id] = _label(record)

    for record in records.get("REQ", []):
        for case in _ids(record.metadata.get("cases")):
            _add(graph, record.id, case, "covered by")
    for record in records.get("TC", []):
        for requirement in _ids(record.metadata.get("requirements")):
            _add(graph, requirement, record.id, "covered by")
        for suite in _ids(record.metadata.get("suites")):
            _add(graph, record.id, suite, "member of")
    for record in records.get("SUITE", []):
        for case in _ids(record.metadata.get("cases")):
            _add(graph, case, record.id, "member of")
    for record in records.get("TP", []):
        for suite in _ids(record.metadata.get("suites")):
            _add(graph, suite, record.id, "part of plan")
        for item in record.metadata.get("selection") or []:
            if isinstance(item, dict) and item.get("decision") == "include":
                _add(graph, str(item.get("id")), record.id, "selected by plan")
    for record in records.get("EXEC", []):
        metadata = record.metadata
        for key, relation in (
            ("test_case", "executed"),
            ("suite", "executed"),
            ("plan", "executed under"),
        ):
            for target in _ids(metadata.get(key)):
                _add(graph, target, record.id, relation)
        for target in _ids(metadata.get("evidence")):
            _add(graph, record.id, target, "evidence")
        for target in _ids(metadata.get("bugs")):
            _add(graph, record.id, target, "defect")
    for record in records.get("EVD", []):
        for target in _ids(record.metadata.get("execution")):
            _add(graph, target, record.id, "evidence")
    return graph


def _walk(graph: TraceGraph, start: str, direction: int) -> dict[str, set[str]]:
    """Follow links monotonically up (+1) or down (-1) the chain."""
    reached: dict[str, set[str]] = {}
    frontier = [start]
    seen = {start}
    while frontier:
        current = frontier.pop()
        current_layer = LAYERS[_prefix(current)]
        for other in graph.neighbours(current):
            other_layer = LAYERS[_prefix(other)]
            if (other_layer - current_layer) * direction <= 0 or other in seen:
                continue
            seen.add(other)
            frontier.append(other)
            reached.setdefault(_prefix(other), set()).add(other)
    return reached


def trace(graph: TraceGraph, record_id: str) -> Trace:
    """The upstream and downstream chain of a record."""
    _prefix(record_id)
    down = _walk(graph, record_id, +1)
    up = _walk(graph, record_id, -1)
    return Trace(
        record_id,
        {kind: tuple(sorted(ids)) for kind, ids in sorted(up.items())},
        {kind: tuple(sorted(ids)) for kind, ids in sorted(down.items())},
    )


@dataclass(frozen=True)
class MatrixRow:
    """One requirement with its cases and the latest execution of each."""

    requirement: str
    title: str
    cases: tuple[tuple[str, str], ...]  # (case id, latest execution summary)
    flag: str


def _latest_executions(
    repository: MarkdownRepository,
) -> dict[str, Record]:
    latest: dict[str, Record] = {}
    if "EXEC" not in repository.prefixes:
        return latest
    for record in repository.list_records("EXEC").records:
        case = record.metadata.get("test_case")
        if case and (case not in latest or record.id > latest[case].id):
            latest[case] = record
    return latest


def matrix(repository: MarkdownRepository) -> list[MatrixRow]:
    """Requirements, their cases, and what the latest execution of each said."""
    graph = build_graph(repository)
    latest = _latest_executions(repository)
    rows: list[MatrixRow] = []
    requirements: Iterable[Record] = (
        repository.list_records("REQ").records if "REQ" in repository.prefixes else ()
    )
    for requirement in requirements:
        cases = sorted(
            other
            for other in graph.neighbours(requirement.id)
            if _prefix(other) == "TC"
        )
        entries: list[tuple[str, str]] = []
        for case in cases:
            execution = latest.get(case)
            if execution is None:
                entries.append((case, "not executed"))
            else:
                status = execution.metadata["status"]
                result = execution.metadata.get("result")
                shown = f"{result} (finalized)" if status == "finalized" else status
                entries.append((case, f"{execution.id}: {shown}"))
        if not cases:
            flag = "no test case"
        elif any("not executed" in text for _, text in entries):
            flag = "not executed"
        elif any(": failed" in text for _, text in entries):
            flag = "has failures"
        elif all(": passed" in text for _, text in entries):
            flag = "passed"
        else:
            flag = "in progress or inconclusive"
        rows.append(
            MatrixRow(
                requirement.id, str(requirement.metadata["title"]), tuple(entries), flag
            )
        )
    return rows
