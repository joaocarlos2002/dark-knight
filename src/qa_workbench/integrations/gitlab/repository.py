"""GitLab commits and merge requests, with the files they changed."""

from typing import Any

from qa_workbench.integrations.errors import UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient
from qa_workbench.integrations.models import Commit, MergeRequest


def _files(diffs: Any, endpoint: str) -> tuple[str, ...]:
    if not isinstance(diffs, list):
        raise UnexpectedResponseError(
            SYSTEM, "expected a list of diffs", endpoint=endpoint
        )
    try:
        return tuple(str(diff["new_path"]) for diff in diffs)
    except (KeyError, TypeError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a diff is missing {error}", endpoint=endpoint
        ) from error


def commit_from(data: Any, endpoint: str, files: tuple[str, ...] = ()) -> Commit:
    try:
        return Commit(
            sha=str(data["id"]),
            title=str(data["title"]),
            author=str(data.get("author_name", "")),
            date=str(data.get("committed_date") or data.get("created_at", "")),
            files=files,
        )
    except (KeyError, TypeError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a commit is missing {error}", endpoint=endpoint
        ) from error


def merge_request_from(
    data: Any, endpoint: str, files: tuple[str, ...] = ()
) -> MergeRequest:
    try:
        author = data.get("author")
        return MergeRequest(
            iid=int(data["iid"]),
            title=str(data["title"]),
            state=str(data["state"]),
            source_branch=str(data["source_branch"]),
            target_branch=str(data["target_branch"]),
            author=str(author.get("username", "")) if isinstance(author, dict) else "",
            url=str(data.get("web_url", "")),
            updated_at=str(data.get("updated_at", "")),
            files=files,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a merge request is missing {error}", endpoint=endpoint
        ) from error


class GitLabRepository:
    """Implements :class:`RepositorySource` for GitLab."""

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    def list_commits(
        self, *, ref: str | None = None, since: str | None = None, limit: int = 20
    ) -> list[Commit]:
        path = self._client.project_path("/repository/commits")
        params: dict[str, str] = {}
        if ref:
            params["ref_name"] = ref
        if since:
            params["since"] = since
        return [
            commit_from(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]

    def get_commit(self, sha: str) -> Commit:
        """A commit with the paths it changed."""
        path = self._client.project_path(f"/repository/commits/{sha}")
        commit = self._client.get_json(path)
        diff_path = path + "/diff"
        diffs = self._client.get_list(diff_path, limit=500)
        return commit_from(commit, path, _files(diffs, diff_path))

    def list_merge_requests(
        self, *, state: str = "opened", limit: int = 20
    ) -> list[MergeRequest]:
        path = self._client.project_path("/merge_requests")
        params = {"state": state, "order_by": "updated_at", "sort": "desc"}
        return [
            merge_request_from(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]

    def get_merge_request(self, iid: int) -> MergeRequest:
        """A merge request with the paths it changes."""
        path = self._client.project_path(f"/merge_requests/{iid}")
        merge_request = self._client.get_json(path)
        diff_path = path + "/diffs"
        diffs = self._client.get_list(diff_path, limit=500)
        return merge_request_from(merge_request, path, _files(diffs, diff_path))
