"""Reading a GitLab repository: branches, the file tree, one file, and code search.

Read only. File content is untrusted text: callers fence it before it reaches a
person or an AI engine, and secrets in it are masked. Large and binary files are
refused with a clear message instead of being truncated silently.
"""

import base64
import binascii
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from qa_workbench.core.secrets import redact_secrets
from qa_workbench.integrations.errors import IntegrationError, UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient

MAX_FILE_BYTES = 256 * 1024
MAX_MATCH_LINES = 20


class FileRefused(IntegrationError):
    """A file is too large or is not text."""


@dataclass(frozen=True)
class Branch:
    name: str
    default: bool
    protected: bool
    last_commit: str
    last_commit_date: str


@dataclass(frozen=True)
class TreeEntry:
    path: str
    name: str
    kind: str  # "dir" or "file"


@dataclass(frozen=True)
class RepoFile:
    path: str
    ref: str
    size: int
    text: str  # secrets already masked


@dataclass(frozen=True)
class CodeMatch:
    path: str
    line: int
    text: str  # secrets already masked


def _need(data: Any, key: str, endpoint: str) -> Any:
    try:
        return data[key]
    except (KeyError, TypeError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"the reply is missing {error}", endpoint=endpoint
        ) from error


class GitLabFiles:
    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    def default_branch(self) -> str:
        path = self._client.project_path("")
        branch = self._client.get_json(path).get("default_branch")
        if not branch:
            raise UnexpectedResponseError(
                SYSTEM, "the project has no default branch", endpoint=path
            )
        return str(branch)

    def list_branches(self, *, limit: int = 30) -> list[Branch]:
        """Branches, the most recently changed first."""
        path = self._client.project_path("/repository/branches")
        items = self._client.get_list(path, {"sort": "updated_desc"}, limit=limit)
        branches = []
        for item in items:
            commit = item.get("commit") or {}
            branches.append(
                Branch(
                    str(_need(item, "name", path)),
                    bool(item.get("default")),
                    bool(item.get("protected")),
                    str(commit.get("short_id") or commit.get("id", ""))[:8],
                    str(commit.get("committed_date", "")),
                )
            )
        return branches

    def list_tree(
        self, path: str = "", ref: str | None = None, *, limit: int = 200
    ) -> list[TreeEntry]:
        """The entries directly under ``path`` (folders first)."""
        endpoint = self._client.project_path("/repository/tree")
        params = {"ref": ref or self.default_branch()}
        if path.strip("/"):
            params["path"] = path.strip("/")
        entries = [
            TreeEntry(
                str(_need(item, "path", endpoint)),
                str(_need(item, "name", endpoint)),
                "dir" if item.get("type") == "tree" else "file",
            )
            for item in self._client.get_list(endpoint, params, limit=limit)
        ]
        return sorted(entries, key=lambda e: (e.kind != "dir", e.name.lower()))

    def get_file(self, path: str, ref: str | None = None) -> RepoFile:
        """One text file, with secrets masked. Refuses big and binary files."""
        chosen = ref or self.default_branch()
        endpoint = self._client.project_path(
            f"/repository/files/{quote(path.strip('/'), safe='')}"
        )
        data = self._client.get_json(endpoint, {"ref": chosen})
        size = int(_need(data, "size", endpoint))
        if size > MAX_FILE_BYTES:
            raise FileRefused(
                SYSTEM,
                f"{path} is {size} bytes; the limit is {MAX_FILE_BYTES}",
                endpoint=endpoint,
                hint="Read a smaller file, or search the code instead",
            )
        try:
            raw = base64.b64decode(str(_need(data, "content", endpoint)), validate=True)
            text = raw.decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as error:
            raise FileRefused(
                SYSTEM,
                f"{path} is not a text file",
                endpoint=endpoint,
                hint="Only UTF-8 text files can be read",
            ) from error
        if "\x00" in text:
            raise FileRefused(
                SYSTEM,
                f"{path} is not a text file",
                endpoint=endpoint,
                hint="Only UTF-8 text files can be read",
            )
        return RepoFile(path.strip("/"), chosen, size, redact_secrets(text))

    def search_code(
        self, query: str, ref: str | None = None, *, limit: int = 30
    ) -> list[CodeMatch]:
        """Matching lines across the repository, with their paths."""
        endpoint = self._client.project_path("/search")
        params = {"scope": "blobs", "search": query}
        if ref:
            params["ref"] = ref
        matches: list[CodeMatch] = []
        for item in self._client.get_list(endpoint, params, limit=limit):
            start = int(item.get("startline") or 1)
            lines = str(item.get("data") or "").splitlines()[:MAX_MATCH_LINES]
            hit = next(
                (i for i, line in enumerate(lines) if query.lower() in line.lower()),
                0,
            )
            matches.append(
                CodeMatch(
                    str(_need(item, "path", endpoint)),
                    start + hit,
                    redact_secrets(lines[hit].strip() if lines else ""),
                )
            )
        return matches
