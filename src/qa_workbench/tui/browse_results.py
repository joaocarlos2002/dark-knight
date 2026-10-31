"""Rows and detail text for result records: defects, API runs, releases, security.

These records already carry a readable Markdown body written when they were
saved, so the detail is a short header from the metadata followed by that body.
"""

from qa_workbench.security.audit import AuditError, AuditLog
from qa_workbench.security.guard import Approval, ApprovalBook
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.tui.browse import BrowseData, BrowseRow, as_list

BUG_COLUMNS = ("ID", "Classification", "Repro", "Severity", "Title")
API_COLUMNS = ("ID", "Result", "Steps", "Title")
RELEASE_COLUMNS = ("ID", "Risk", "Commits", "Title")
SECURITY_COLUMNS = ("ID", "Kind", "Status", "Summary")


def _row(
    record: Record, cells: tuple[str, ...], status: str, extra: str = ""
) -> BrowseRow:
    return BrowseRow(record.id, cells, status, f"{' '.join(cells)} {extra}".lower())


def _with_body(header: list[str], record: Record) -> str:
    return "\n".join([*header, "", record.body.strip()])


# -- defects ---------------------------------------------------------------


def bug_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("BUG")
    rows = []
    for record in listing.records:
        meta = record.metadata
        repro = f"{meta.get('reproductions', 0)}/{meta.get('attempts', 0)}"
        cells = (
            record.id,
            str(meta["status"]),
            repro,
            str(meta.get("severity") or "-"),
            str(meta["title"]),
        )
        rows.append(_row(record, cells, str(meta["status"])))
    return BrowseData(tuple(rows), tuple(f"BUG: {e}" for e in listing.errors))


def bug_detail(repository: MarkdownRepository, record_id: str) -> str:
    record = repository.get(record_id)
    meta = record.metadata
    header = [
        f"{record.id}  {meta['title']}",
        f"Found by {meta['found_by']}   Environment {meta['environment']}",
    ]
    history = [h for h in meta.get("classification_history", []) if isinstance(h, dict)]
    if meta.get("gitlab_issue_url"):
        header.append(f"GitLab issue: {meta['gitlab_issue_url']}")
    text = _with_body(header, record)
    if history:
        text += "\n\nCLASSIFICATION HISTORY\n" + "\n".join(
            f"  {h.get('from')} -> {h.get('to')} by {h.get('by')}: {h.get('why')}"
            for h in history
        )
    return text


# -- API runs ------------------------------------------------------------------------


def api_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("API")
    rows = []
    for record in listing.records:
        meta = record.metadata
        steps = meta.get("steps") if isinstance(meta.get("steps"), list) else []
        passed = sum(
            1 for s in steps if isinstance(s, dict) and s.get("status") == "passed"
        )
        cells = (
            record.id,
            str(meta["status"]),
            f"{passed}/{len(steps)}",
            str(meta["title"]),
        )
        rows.append(
            _row(record, cells, str(meta["status"]), str(meta.get("base_url", "")))
        )
    return BrowseData(tuple(rows), tuple(f"API: {e}" for e in listing.errors))


def api_detail(repository: MarkdownRepository, record_id: str) -> str:
    record = repository.get(record_id)
    meta = record.metadata
    header = [
        f"{record.id}  {meta['title']}",
        f"Result {meta['status']}   Target {meta.get('base_url', '-')}"
        + (f"   Execution {meta['execution']}" if meta.get("execution") else ""),
        "Requests and responses below were sanitized before they were saved.",
    ]
    return _with_body(header, record)


# -- release analyses ------------------------------------------------------


def release_rows(repository: MarkdownRepository) -> BrowseData:
    listing = repository.list_records("REL")
    rows = []
    for record in listing.records:
        meta = record.metadata
        cells = (
            record.id,
            str(meta["risk_level"]),
            str(len(as_list(meta.get("commits")))),
            str(meta["title"]),
        )
        rows.append(_row(record, cells, str(meta["risk_level"])))
    return BrowseData(tuple(rows), tuple(f"REL: {e}" for e in listing.errors))


def release_detail(repository: MarkdownRepository, record_id: str) -> str:
    record = repository.get(record_id)
    meta = record.metadata
    header = [
        f"{record.id}  {meta['title']}",
        f"Risk {meta['risk_level']}   Scope {meta['scope']}   "
        f"{len(as_list(meta.get('commits')))} commit(s)",
    ]
    return _with_body(header, record)


# -- security: approval requests and security-check runs ------------------------------


def approval_cells(approval: Approval) -> tuple[str, ...]:
    return (
        approval.request_id,
        "approval",
        approval.status,
        f"{approval.action} ({approval.category})",
    )


def security_rows(repository: MarkdownRepository) -> BrowseData:
    rows: list[BrowseRow] = []
    problems: list[str] = []
    try:
        for approval in ApprovalBook(AuditLog(repository.root)).all():
            cells = approval_cells(approval)
            rows.append(
                BrowseRow(
                    approval.request_id,
                    cells,
                    approval.status,
                    f"{' '.join(cells)} {approval.requested_by} "
                    f"{approval.detail}".lower(),
                )
            )
    except AuditError as error:
        problems.append(f"audit log: {error}")
    listing = repository.list_records("SEC")
    problems.extend(f"SEC: {e}" for e in listing.errors)
    for record in listing.records:
        meta = record.metadata
        summary = (
            f"{meta['confirmed']} confirmed, {meta['hypotheses']} hypotheses "
            f"on {meta['target']}"
        )
        cells = (record.id, "security-check", str(meta["status"]), summary)
        rows.append(_row(record, cells, str(meta["status"])))
    return BrowseData(tuple(rows), tuple(problems))


def security_detail(repository: MarkdownRepository, key: str) -> str:
    if key.startswith("APR-"):
        book = ApprovalBook(AuditLog(repository.root))
        approval = book.get(key)
        if approval is None:
            return f"{key} (approval request not found)"
        lines = [
            f"{approval.request_id}  {approval.status.upper()}",
            f"Action: {approval.action}   Category: {approval.category}",
            f"Requested by: {approval.requested_by}",
            f"Detail: {approval.detail or '-'}",
        ]
        if approval.decided_by:
            lines.append(f"Decided by {approval.decided_by}: {approval.reason or '-'}")
        elif approval.status == "pending":
            lines += ["", "A person must decide: A approves, D denies."]
        lines += ["", "An approval covers exactly this action, once, for one hour."]
        return "\n".join(lines)
    record = repository.get(key)
    meta = record.metadata
    header = [
        f"{record.id}  {meta['title']}",
        f"Authorized by {meta['authorized_by']}   Status {meta['status']}",
    ]
    return _with_body(header, record)


def audit_summary(repository: MarkdownRepository) -> str:
    try:
        entries = AuditLog(repository.root).entries()
    except AuditError as error:
        return f"AUDIT LOG DAMAGED: {error}"
    return f"Audit log intact: {len(entries)} entries."
