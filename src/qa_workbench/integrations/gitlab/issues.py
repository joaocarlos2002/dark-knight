"""GitLab issues and their comments."""

from typing import Any

from qa_workbench.integrations.errors import UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient
from qa_workbench.integrations.models import Issue, Note


def _author(data: dict[str, Any]) -> str:
    author = data.get("author")
    return str(author.get("username", "")) if isinstance(author, dict) else ""


def issue_from(data: Any, endpoint: str) -> Issue:
    try:
        return Issue(
            iid=int(data["iid"]),
            title=str(data["title"]),
            description=str(data.get("description") or ""),
            state=str(data["state"]),
            labels=tuple(str(label) for label in data.get("labels", [])),
            author=_author(data),
            url=str(data.get("web_url", "")),
            updated_at=str(data.get("updated_at", "")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"an issue is missing {error}", endpoint=endpoint
        ) from error


def note_from(data: Any, endpoint: str) -> Note:
    try:
        return Note(
            id=int(data["id"]),
            author=_author(data),
            body=str(data.get("body") or ""),
            created_at=str(data.get("created_at", "")),
            system=bool(data.get("system", False)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a note is missing {error}", endpoint=endpoint
        ) from error


class GitLabIssues:
    """Implements :class:`IssueSource` for GitLab."""

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    def list_issues(
        self,
        *,
        state: str = "opened",
        labels: tuple[str, ...] = (),
        limit: int = 20,
        include_test_cases: bool = False,
    ) -> list[Issue]:
        """Features and bugs. Test cases are issues too, so they are left out
        unless asked for."""
        path = self._client.project_path("/issues")
        params = {"state": state, "order_by": "updated_at", "sort": "desc"}
        if labels:
            params["labels"] = ",".join(labels)
        if not include_test_cases:
            params["not[labels]"] = "type::testcase"
        return [
            issue_from(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]

    def get_issue(self, iid: int) -> Issue:
        """The issue with its comments."""
        path = self._client.project_path(f"/issues/{iid}")
        issue = issue_from(self._client.get_json(path), path)
        return Issue(**{**issue.__dict__, "notes": tuple(self.list_notes(iid))})

    def list_notes(self, iid: int, *, limit: int = 100) -> list[Note]:
        path = self._client.project_path(f"/issues/{iid}/notes")
        params = {"order_by": "created_at", "sort": "asc"}
        return [
            note_from(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]
