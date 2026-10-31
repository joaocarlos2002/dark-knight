"""GitLab boards across the whole group, and an issue's links.

The team's boards are group-level: a board is a filter label plus a column label,
and a column mixes issues from several projects. Reading a column means filtering
the group's issues on both labels (labels are ANDed). Test cases are issues too
(``type::testcase``), so they are kept out unless asked for. Read only.
"""

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from qa_workbench.integrations.errors import UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient

TESTCASE_LABEL = "type::testcase"


@dataclass(frozen=True)
class GroupIssue:
    project: str  # the project path, such as nees/primeira-infancia/frontend
    iid: int
    title: str
    state: str
    labels: tuple[str, ...]
    url: str
    assignees: tuple[str, ...]

    @property
    def reference(self) -> str:
        return f"{self.project}#{self.iid}"


@dataclass(frozen=True)
class LinkedItem:
    kind: str  # "related issue", "related merge request", or "closed by"
    reference: str
    title: str
    state: str
    url: str


def _project_of(item: dict[str, Any]) -> str:
    full = str((item.get("references") or {}).get("full") or "")
    if "#" in full:
        return full.rpartition("#")[0]
    url = str(item.get("web_url") or "")
    marker = "/-/"
    return url.partition(marker)[0].split("/", 3)[-1] if marker in url else ""


def _group_issue(item: Any, endpoint: str) -> GroupIssue:
    try:
        return GroupIssue(
            _project_of(item),
            int(item["iid"]),
            str(item["title"]),
            str(item.get("state", "")),
            tuple(str(label) for label in item.get("labels") or []),
            str(item.get("web_url", "")),
            tuple(
                str(a.get("username", ""))
                for a in item.get("assignees") or []
                if isinstance(a, dict)
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"an issue is missing {error}", endpoint=endpoint
        ) from error


class GitLabBoard:
    """Reads a group's issues the way its boards group them."""

    def __init__(self, client: GitLabClient, group: str) -> None:
        if not group.strip():
            raise ValueError("The board group is empty.")
        self._client = client
        self._group = quote(group.strip(), safe="")

    def column(
        self,
        labels: tuple[str, ...],
        *,
        state: str = "opened",
        project: str = "",
        include_test_cases: bool = False,
        limit: int = 100,
    ) -> list[GroupIssue]:
        """Issues that carry every label (a board's filter label and a column
        label), from all projects of the group, or only from ``project``."""
        path = f"/groups/{self._group}/issues"
        params = {"state": state, "order_by": "updated_at", "sort": "desc"}
        if labels:
            params["labels"] = ",".join(labels)
        if not include_test_cases:
            params["not[labels]"] = TESTCASE_LABEL
        issues = [
            _group_issue(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]
        if project:
            wanted = project.strip("/").lower()
            issues = [i for i in issues if i.project.lower() == wanted]
        return issues


class GitLabIssueLinks:
    """Related issues, related merge requests, and the merge requests that close
    an issue, for an issue of the client's project."""

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    def links(self, iid: int) -> list[LinkedItem]:
        found: list[LinkedItem] = []
        for kind, suffix in (
            ("related issue", "/links"),
            ("related merge request", "/related_merge_requests"),
            ("closed by", "/closed_by"),
        ):
            path = self._client.project_path(f"/issues/{iid}{suffix}")
            for item in self._client.get_list(path, limit=100):
                try:
                    full = str((item.get("references") or {}).get("full") or "")
                    marker = "#" if kind == "related issue" else "!"
                    found.append(
                        LinkedItem(
                            kind,
                            full or f"{marker}{item['iid']}",
                            str(item["title"]),
                            str(item.get("state", "")),
                            str(item.get("web_url", "")),
                        )
                    )
                except (KeyError, TypeError, AttributeError) as error:
                    raise UnexpectedResponseError(
                        SYSTEM, f"a link is missing {error}", endpoint=path
                    ) from error
        return found
