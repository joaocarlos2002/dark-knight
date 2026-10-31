"""Push a local test case to GitLab as a ``test_case`` issue, with approval.

Creating or changing an issue is visible to the whole team, so it is an outward
action: it needs a person's approval bound to this exact content (the guard
fingerprints the action, and the SHA-256 of the text is part of it), and every
write is audited. Pushing the same, unchanged case again does nothing. If GitLab
already has a case with the same title it is updated, never copied, and only the
sections that changed are rewritten.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from qa_workbench.integrations.errors import IntegrationError, UnreachableError
from qa_workbench.integrations.gitlab.test_cases import (
    TESTCASE_LABEL,
    GitLabTestCases,
    RemoteCase,
    merge_description,
    render_description,
    render_sections,
)
from qa_workbench.integrations.gitlab.wiki import requirement_codes
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.storage.repository import MarkdownRepository, Record


class PushError(Exception):
    """The case cannot be pushed (not found, deprecated, or GitLab refused)."""


@dataclass(frozen=True)
class PushResult:
    action: str  # "created", "updated", or "unchanged"
    iid: int
    url: str


def _requirements(repository: MarkdownRepository, record: Record) -> list[Record]:
    found = []
    for requirement_id in record.metadata.get("requirements") or []:
        try:
            found.append(repository.get(str(requirement_id)))
        except Exception:  # a dangling reference is shown as no link, not a crash
            continue
    return found


def build_content(
    repository: MarkdownRepository, record: Record
) -> tuple[str, list[tuple[str, str]], list[str]]:
    """The title, the sections of the standard layout, and the labels."""
    meta = record.metadata
    requirements = _requirements(repository, record)
    rules: list[str] = []
    related: list[tuple[str, str]] = []
    codes: list[str] = []
    for requirement in requirements:
        rules += [str(r) for r in requirement.metadata.get("business_rules") or []]
        found = requirement_codes(
            *[str(t) for t in requirement.metadata.get("tags") or []]
        )
        codes += found
        url = str(requirement.metadata.get("source_url") or "")
        if url:
            related.append(((found[-1] if found else requirement.id), url))
    sections = render_sections(
        objective=str(meta.get("objective") or ""),
        preconditions=[str(p) for p in meta.get("preconditions") or []],
        steps=[s for s in meta.get("steps") or [] if isinstance(s, dict)],
        expected_result=str(meta.get("expected_result") or ""),
        coverage=", ".join(dict.fromkeys(rules)),
        related=related,
    )
    labels = list(dict.fromkeys([*codes, TESTCASE_LABEL]))
    return str(meta["title"]), sections, labels


def push_case(
    repository: MarkdownRepository,
    case_id: str,
    *,
    guard: ActionGuard,
    remote: GitLabTestCases,
    actor: str,
) -> PushResult:
    """Create or update the GitLab test case. Raises ``ApprovalRequired`` until a
    person approves this exact content."""
    record = repository.get(case_id)
    meta = record.metadata
    if not case_id.startswith("TC-"):
        raise PushError(f"{case_id} is not a test case.")
    if meta["status"] == "deprecated":
        raise PushError(f"{case_id} is deprecated and is not pushed.")
    title, sections, labels = build_content(repository, record)
    description = render_description(title, sections)
    digest = sha256(description.encode("utf-8")).hexdigest()
    iid = meta.get("gitlab_iid")
    if iid and meta.get("gitlab_sha256") == digest:
        return PushResult("unchanged", int(iid), str(meta.get("gitlab_url", "")))

    existing: RemoteCase | None = None
    verb = "update" if iid else "create"
    guard.authorize(
        ActionRequest(
            "push test case",
            Category.EXTERNAL_COMMENT,
            f"{verb} test case {case_id} sha256:{digest}",
            target_url=remote.issues_url,
            requested_by=actor,
        )
    )
    try:
        if iid:
            existing = remote.get_case(int(iid))
        elif labels[0] != TESTCASE_LABEL:
            existing = remote.find(title, labels[0])
        if existing is not None:
            merged = merge_description(existing.description, sections)
            written = remote.update(existing.iid, merged, labels)
            action = "updated"
        else:
            written = remote.create(title, description, labels)
            action = "created"
    except UnreachableError as error:
        guard.audit.append(
            "test_case_push_unknown", actor, {"case": case_id, "error": str(error)}
        )
        raise PushError(
            f"{error} The write may have been applied: check GitLab before retrying."
        ) from error
    except IntegrationError as error:
        guard.audit.append(
            "test_case_push_failed", actor, {"case": case_id, "error": str(error)}
        )
        raise PushError(str(error)) from error

    repository.update(
        case_id,
        {
            "gitlab_iid": written.iid,
            "gitlab_url": written.url,
            "gitlab_sha256": digest,
            "gitlab_pushed_at": datetime.now(UTC).astimezone(),
        },
    )
    guard.audit.append(
        "test_case_pushed",
        actor,
        {"case": case_id, "iid": written.iid, "action": action, "sha256": digest},
    )
    return PushResult(action, written.iid, written.url)
