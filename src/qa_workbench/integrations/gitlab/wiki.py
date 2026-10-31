"""Reading the GitLab group wiki (REQ-026).

The team keeps its requirements in the **group** wiki, under a prefix such as
``Requisitos/``. Slugs are path-like and may hold accents; they are passed
unencoded and encoded here. The wiki is read only. Page text is untrusted: it is
fenced before it reaches a person or an AI engine.
"""

import re
from dataclasses import dataclass
from urllib.parse import quote

from qa_workbench.integrations.errors import UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient

DEFAULT_PREFIX = "Requisitos/"
# A requirement code such as GE01.01 or S02, and a business rule such as
# RN-GE01.01.08. The rule is matched first so its code is not read on its own.
_RULE = re.compile(r"\bRN-[A-Z]{1,3}\d{2}(?:\.\d{1,3})*(?:[.-]\d{1,3})*\b")
_CODE = re.compile(r"\b[A-Z]{1,3}\d{2}(?:\.\d{2,3})*\b")


@dataclass(frozen=True)
class WikiPage:
    slug: str
    title: str
    content: str = ""
    format: str = "markdown"


def group_of(project_path: str) -> str:
    """The group that holds a project: its path without the last segment."""
    group, _, _ = project_path.strip("/").rpartition("/")
    return group


def page_url(base_url: str, group: str, slug: str) -> str:
    return f"{base_url.rstrip('/')}/groups/{group}/-/wikis/{quote(slug, safe='/')}"


def business_rules(text: str) -> list[str]:
    return list(dict.fromkeys(_RULE.findall(text)))


def requirement_codes(*texts: str) -> list[str]:
    """Requirement codes found in the texts, never the code inside a rule."""
    found: list[str] = []
    for text in texts:
        found.extend(_CODE.findall(_RULE.sub(" ", text)))
    return list(dict.fromkeys(found))


def _page_from(data: object, endpoint: str) -> WikiPage:
    if not isinstance(data, dict) or not isinstance(data.get("slug"), str):
        raise UnexpectedResponseError(
            SYSTEM, "a wiki page has no slug", endpoint=endpoint
        )
    return WikiPage(
        data["slug"],
        str(data.get("title") or data["slug"].rsplit("/", 1)[-1]),
        str(data.get("content") or ""),
        str(data.get("format") or "markdown"),
    )


class GitLabWiki:
    """Reads one group's wiki through a project-bound client (same host, token)."""

    def __init__(self, client: GitLabClient, group: str) -> None:
        if not group.strip():
            raise ValueError("The wiki group is empty.")
        self._client = client
        self._group = quote(group.strip(), safe="")

    def _path(self, suffix: str = "") -> str:
        return f"/groups/{self._group}/wikis{suffix}"

    def list_pages(
        self,
        prefix: str = DEFAULT_PREFIX,
        *,
        with_content: bool = False,
        limit: int = 500,
    ) -> list[WikiPage]:
        params = {"with_content": "1"} if with_content else {}
        path = self._path()
        data = self._client.get_list(path, params, limit=limit)
        pages = [_page_from(item, path) for item in data]
        wanted = prefix.lower()
        return [p for p in pages if p.slug.lower().startswith(wanted)]

    def get_page(self, slug: str) -> WikiPage:
        path = self._path(f"/{quote(slug, safe='')}")
        return _page_from(self._client.get_json(path), path)

    def search(self, query: str, prefix: str = DEFAULT_PREFIX) -> list[WikiPage]:
        """Pages whose title or slug contains every word of ``query``."""
        words = query.lower().split()
        return [
            p
            for p in self.list_pages(prefix)
            if all(w in f"{p.title} {p.slug}".lower() for w in words)
        ]
