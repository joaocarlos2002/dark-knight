"""``SEC`` records: the sanitized, sealed result of a security-check run."""

from qa_workbench.api.sanitize import Sanitizer
from qa_workbench.core.secrets import find_secrets
from qa_workbench.sectest.runner import SecurityRun
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.storage.validation import RecordSchema

COMPLETED = "completed"
INCOMPLETE = "incomplete"

SEC_SCHEMA = RecordSchema(
    prefix="SEC",
    directory="security-tests",
    statuses=frozenset({COMPLETED, INCOMPLETE}),
    required=("title", "target", "authorized_by", "confirmed", "hypotheses"),
    immutable_statuses=frozenset({COMPLETED, INCOMPLETE}),
)

DISCLAIMER = (
    "These are limited, passive, automated checks. They are not a penetration "
    "test and not an OWASP, ISTQB, or any other certification, and a check that "
    "found nothing does not show that the target is secure."
)


class UnsafeToSaveError(Exception):
    """The result still looked like it held a credential, so it was not saved."""


def render(run: SecurityRun, sanitizer: Sanitizer) -> str:
    lines = [f"# Security checks: {sanitizer.url(run.url)}", "", DISCLAIMER, ""]
    lines += [f"Authorized by {run.authorized_by}.", "", "## Checks run", ""]
    for item in run.checks:
        if item.outcome is None:
            lines.append(f"- {item.check}: ERROR - {sanitizer.text(item.error)}")
            continue
        note = f" ({item.outcome.note})" if item.outcome.note else ""
        lines.append(
            f"- {item.check}: {item.outcome.requests} request(s), "
            f"{len(item.outcome.findings)} finding(s){note}"
        )
    for confirmed, heading in ((True, "Confirmed findings"), (False, "Hypotheses")):
        group = [f for f in run.findings if f.confirmed is confirmed]
        lines += ["", f"## {heading}", ""]
        for finding in group:
            reference = f" [{finding.reference}]" if finding.reference else ""
            lines.append(f"- **{finding.severity}** {finding.title}{reference}")
            lines.append(f"  {sanitizer.text(finding.detail)}")
        if not group:
            lines.append("None.")
    return "\n".join(lines).rstrip() + "\n"


def save_run(repository: MarkdownRepository, run: SecurityRun) -> Record:
    body = render(run, Sanitizer())
    leaks = find_secrets(body)
    if leaks:
        raise UnsafeToSaveError(
            f"The result still contains {', '.join(sorted(set(leaks)))}; nothing was "
            "saved. Report this as a sanitizer bug."
        )
    findings = run.findings
    fields = {
        "status": COMPLETED if run.ok else INCOMPLETE,
        "title": f"Security checks on {Sanitizer().url(run.url)}",
        "target": Sanitizer().url(run.url),
        "authorized_by": run.authorized_by,
        "checks": [c.check for c in run.checks],
        "confirmed": sum(1 for f in findings if f.confirmed),
        "hypotheses": sum(1 for f in findings if not f.confirmed),
    }
    return repository.create("SEC", fields, body)
