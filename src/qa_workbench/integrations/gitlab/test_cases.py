"""GitLab test cases: issues of type ``test_case`` in the team's standard layout.

The layout is a contract that people and tooling read, so its headings and the
steps table are stable. Updating never rewrites a body wholesale: only the
sections that changed are replaced and every other character stays as it was, so
the diff in GitLab shows the change alone.
"""

import re
from dataclasses import dataclass
from typing import Any

from qa_workbench.integrations.errors import IntegrationError, UnexpectedResponseError
from qa_workbench.integrations.gitlab.client import SYSTEM, GitLabClient

TESTCASE_LABEL = "type::testcase"

OBJECTIVE = "Objetivo"
PRECONDITIONS = "Pré-condições"
STEPS = "Passos"
EXPECTED = "Resultado Esperado"
COVERAGE = "Critérios/Cobertura"
RELATED = "🔗 Requisitos relacionados"

_HEADING = re.compile(r"^## (.*?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class RemoteCase:
    iid: int
    title: str
    description: str
    labels: tuple[str, ...]
    url: str
    state: str


def _cell(text: str) -> str:
    """One line, with the table separator escaped."""
    return " ".join(str(text).split()).replace("|", "\\|")


def render_sections(
    *,
    objective: str,
    preconditions: list[str],
    steps: list[dict[str, str]],
    expected_result: str,
    coverage: str,
    related: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """The sections of the standard layout, in order, as (heading, body)."""
    table = [
        "| Passo | Ação | Resultado Esperado |",
        "|-------|------|---------------------|",
    ]
    for number, step in enumerate(steps, start=1):
        table.append(
            f"| {number} | {_cell(step.get('action', ''))} "
            f"| {_cell(step.get('expected', ''))} |"
        )
    sections = [
        (OBJECTIVE, objective.strip() or "-"),
        (PRECONDITIONS, "\n".join(f"- {p}" for p in preconditions) or "-"),
        (STEPS, "\n".join(table)),
        (EXPECTED, expected_result.strip() or "-"),
        (COVERAGE, coverage.strip() or "-"),
    ]
    if related:
        sections.append(
            (RELATED, "\n".join(f"- {name} — {url}" for name, url in related))
        )
    return sections


def render_description(title: str, sections: list[tuple[str, str]]) -> str:
    parts = [f"# {title}"] + [f"## {name}\n{body}" for name, body in sections]
    return "\n\n".join(parts) + "\n"


def merge_description(existing: str, sections: list[tuple[str, str]]) -> str:
    """``existing`` with only the changed sections rewritten.

    A section that already has the same text is left byte for byte as it was,
    sections this tool does not know are kept, and a missing section is appended.
    """
    text = existing.replace("\r\n", "\n")
    marks = list(_HEADING.finditer(text))
    pieces: list[str] = [text[: marks[0].start()] if marks else text]
    present: dict[str, int] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        pieces.append(text[mark.start() : end])
        present[mark.group(1)] = len(pieces) - 1
    for name, body in sections:
        chunk_at = present.get(name)
        if chunk_at is not None:
            current = (
                pieces[chunk_at].split("\n", 1)[1] if "\n" in pieces[chunk_at] else ""
            )
            if current.strip() == body.strip():
                continue
            trailing = pieces[chunk_at][len(pieces[chunk_at].rstrip("\n")) :]
            pieces[chunk_at] = f"## {name}\n{body}{trailing or chr(10) * 2}"
        else:
            last = pieces[-1]
            if not last.endswith("\n\n"):
                pieces[-1] = last.rstrip("\n") + "\n\n"
            pieces.append(f"## {name}\n{body}\n")
            present[name] = len(pieces) - 1
    return "".join(pieces)


def _case_from(data: Any, endpoint: str) -> RemoteCase:
    try:
        return RemoteCase(
            int(data["iid"]),
            str(data["title"]),
            str(data.get("description") or ""),
            tuple(str(label) for label in data.get("labels") or []),
            str(data.get("web_url", "")),
            str(data.get("state", "")),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UnexpectedResponseError(
            SYSTEM, f"a test case is missing {error}", endpoint=endpoint
        ) from error


class GitLabTestCases:
    """Reads and writes ``test_case`` issues of one project."""

    def __init__(self, client: GitLabClient) -> None:
        self._client = client

    @property
    def issues_url(self) -> str:
        return f"{self._client.base_url}/{self._client.project_name}/-/issues"

    def list_cases(self, label: str = "", *, limit: int = 100) -> list[RemoteCase]:
        """Test cases, optionally only those with a label (a requirement code).
        Test cases never show up in ordinary issue listings."""
        path = self._client.project_path("/issues")
        params = {"issue_type": "test_case", "state": "all"}
        if label:
            params["labels"] = label
        return [
            _case_from(item, path)
            for item in self._client.get_list(path, params, limit=limit)
        ]

    def get_case(self, iid: int) -> RemoteCase:
        path = self._client.project_path(f"/issues/{iid}")
        return _case_from(self._client.get_json(path), path)

    def find(self, title: str, label: str = "") -> RemoteCase | None:
        """An existing case with this exact title (so it is updated, not copied)."""
        wanted = title.strip().lower()
        return next(
            (c for c in self.list_cases(label) if c.title.strip().lower() == wanted),
            None,
        )

    def create(self, title: str, description: str, labels: list[str]) -> RemoteCase:
        path = self._client.project_path("/issues")
        reply = self._client.post_json(
            path,
            {
                "title": title,
                "description": description,
                "labels": ",".join(labels),
                "issue_type": "test_case",
            },
        )
        return self._written(reply, path)

    def update(self, iid: int, description: str, labels: list[str]) -> RemoteCase:
        path = self._client.project_path(f"/issues/{iid}")
        reply = self._client.put_json(
            path, {"description": description, "add_labels": ",".join(labels)}
        )
        return self._written(reply, path)

    @staticmethod
    def _written(reply: Any, path: str) -> RemoteCase:
        try:
            return _case_from(reply, path)
        except IntegrationError as error:
            raise UnexpectedResponseError(
                SYSTEM,
                "the reply to the write has no test case",
                endpoint=path,
                hint="It may have been applied; check GitLab before retrying",
            ) from error
