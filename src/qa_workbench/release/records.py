"""``REL`` records: a saved release analysis, sealed like any result."""

from qa_workbench.release.analysis import ReleaseAnalysis
from qa_workbench.storage.repository import MarkdownRepository, Record
from qa_workbench.storage.validation import RecordSchema

COMPLETED = "completed"

RELEASE_SCHEMA = RecordSchema(
    prefix="REL",
    directory="releases",
    statuses=frozenset({COMPLETED}),
    required=("title", "scope", "risk_level", "commits"),
    immutable_statuses=frozenset({COMPLETED}),
)


def render(analysis: ReleaseAnalysis) -> str:
    lines = [f"# Release analysis ({analysis.scope})", ""]
    lines += ["## Summary of changes", ""]
    lines.append(
        f"{len(analysis.commits)} commit(s), {len(analysis.files)} file(s), "
        f"{len(analysis.merge_requests)} merged merge request(s)."
    )
    for commit in analysis.commits:
        lines.append(
            f"- `{commit.sha[:10]}` {commit.title} ({len(commit.files)} files)"
        )
    for mr in analysis.merge_requests:
        lines.append(
            f"- !{mr.iid} {mr.title} ({mr.source_branch} -> {mr.target_branch})"
        )
    lines += ["", "## Risk areas", ""]
    for area in analysis.areas:
        lines.append(f"### {area.area}: {area.level}")
        lines.append(
            "Reasons: " + ("; ".join(area.reasons) if area.reasons else "none found")
        )
        lines.append("Commits: " + ", ".join(f"`{sha[:10]}`" for sha in area.commits))
        lines.append("Files: " + ", ".join(f"`{f}`" for f in area.files))
        lines.append("")
    if not analysis.areas:
        lines += ["No changed files were reported.", ""]
    lines += ["## Potentially impacted cases", ""]
    for case in analysis.impacted_cases:
        lines.append(
            f"- [[{case.case_id}]] {case.title} (matched: {', '.join(case.matched)})"
        )
    if not analysis.impacted_cases:
        lines.append("None matched the changed paths.")
    lines += ["", "## Recommended suites", ""]
    for suite in analysis.suites:
        lines.append(f"- [[{suite.suite_id}]] {suite.title}: {suite.why}")
    if not analysis.suites:
        lines.append("None.")
    lines += ["", "## Regression recommendation", "", analysis.regression, ""]
    lines += ["## Justification", ""] + [f"- {line}" for line in analysis.justification]
    lines += ["", "## Limitations", ""] + [f"- {line}" for line in analysis.limitations]
    return "\n".join(lines).rstrip() + "\n"


def save_analysis(repository: MarkdownRepository, analysis: ReleaseAnalysis) -> Record:
    fields = {
        "status": COMPLETED,
        "title": f"Release analysis ({analysis.scope})",
        "scope": analysis.scope,
        "risk_level": analysis.risk_level,
        "commits": [c.sha for c in analysis.commits],
    }
    return repository.create("REL", fields, render(analysis))
