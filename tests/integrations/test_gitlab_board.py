import re
from pathlib import Path

import pytest
from fake_gitlab import PREFIX, TOKEN, FakeGateway, make_client
from typer.testing import CliRunner

from qa_workbench.integrations.gitlab import cli
from qa_workbench.integrations.gitlab.board import GitLabBoard, GitLabIssueLinks
from qa_workbench.main import app

runner = CliRunner()
GROUP = "/api/v4/groups/group/issues"
URL = "https://gitlab.test/group/app"


def _issue(project: str, iid: int, title: str, *labels: str) -> dict:
    return {
        "iid": iid,
        "title": title,
        "state": "opened",
        "labels": list(labels),
        "web_url": f"https://gitlab.test/{project}/-/issues/{iid}",
        "references": {"full": f"{project}#{iid}"},
        "assignees": [{"username": "ada"}],
    }


ISSUES = [
    _issue("group/frontend", 12, "Botão quebrado", "team::dev", "workflow::QA"),
    _issue("group/backend", 3, "API lenta", "team::dev", "workflow::QA"),
]


def test_a_column_is_read_across_the_group_with_both_labels() -> None:
    gateway = FakeGateway({GROUP: ISSUES})

    issues = GitLabBoard(make_client(gateway), "group").column(
        ("team::dev", "workflow::QA")
    )

    params = gateway.requests[0].params
    assert params["labels"] == "team::dev,workflow::QA"
    assert params["not[labels]"] == "type::testcase"
    assert [i.reference for i in issues] == ["group/frontend#12", "group/backend#3"]
    assert issues[0].assignees == ("ada",) and issues[0].labels[0] == "team::dev"


def test_test_cases_are_only_included_when_asked_for() -> None:
    gateway = FakeGateway({GROUP: ISSUES})
    board = GitLabBoard(make_client(gateway), "group")

    board.column(("team::dev",), include_test_cases=True)

    assert "not[labels]" not in gateway.requests[0].params


def test_a_column_can_be_narrowed_to_one_project() -> None:
    board = GitLabBoard(make_client(FakeGateway({GROUP: ISSUES})), "group")

    only = board.column(("team::dev",), project="group/backend")

    assert [i.reference for i in only] == ["group/backend#3"]


def test_the_project_falls_back_to_the_url_when_references_are_missing() -> None:
    bare = {k: v for k, v in ISSUES[0].items() if k != "references"}
    board = GitLabBoard(make_client(FakeGateway({GROUP: [bare]})), "group")

    assert board.column(())[0].reference == "group/frontend#12"


def test_links_cover_related_issues_and_merge_requests() -> None:
    gateway = FakeGateway(
        {
            PREFIX + "/issues/7/links": [
                {
                    "iid": 8,
                    "title": "Irmã",
                    "state": "opened",
                    "references": {"full": "group/app#8"},
                }
            ],
            PREFIX + "/issues/7/related_merge_requests": [
                {
                    "iid": 4,
                    "title": "Tenta",
                    "state": "opened",
                    "references": {"full": "group/app!4"},
                }
            ],
            PREFIX + "/issues/7/closed_by": [
                {
                    "iid": 5,
                    "title": "Corrige",
                    "state": "merged",
                    "references": {"full": "group/app!5"},
                }
            ],
        }
    )

    links = GitLabIssueLinks(make_client(gateway)).links(7)

    assert [(link.kind, link.reference) for link in links] == [
        ("related issue", "group/app#8"),
        ("related merge request", "group/app!4"),
        ("closed by", "group/app!5"),
    ]


# -- the commands ----------------------------------------------------------------


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeGateway:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
    gateway = FakeGateway(
        {
            GROUP: ISSUES,
            PREFIX + "/issues": [_issue("group/app", 1, "Feature", "type::feature")],
            PREFIX + "/issues/7/links": [],
            PREFIX + "/issues/7/related_merge_requests": [],
            PREFIX + "/issues/7/closed_by": [],
            "/api/v4/projects/group%2Fother/issues": [],
        }
    )
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    runner.invoke(app, ["project", "create", "Demo", "--repository", URL])
    allow = ["security", "set", "-p", "PROJ-001", "--allow-host", "gitlab.test"]
    assert runner.invoke(app, [*allow, "--by", "Ana"]).exit_code == 0
    return gateway


def test_the_board_command_shows_project_title_labels_and_assignee(served) -> None:
    result = runner.invoke(
        app,
        ["gitlab", "board", "-p", "PROJ-001", "--labels", "team::dev,workflow::QA"],
    )
    out = _plain(result.output)

    assert result.exit_code == 0, out
    assert "group/frontend#12" in out and "Botão quebrado" in out and "@ada" in out
    assert served.requests[0].params["labels"] == "team::dev,workflow::QA"


def test_issues_leave_test_cases_out_and_links_read_another_project(served) -> None:
    runner.invoke(app, ["gitlab", "issues", "-p", "PROJ-001"])
    assert served.requests[0].params["not[labels]"] == "type::testcase"
    runner.invoke(app, ["gitlab", "issues", "-p", "PROJ-001", "--include-test-cases"])
    assert "not[labels]" not in served.requests[1].params

    out = _plain(
        runner.invoke(app, ["gitlab", "issue-links", "7", "-p", "PROJ-001"]).output
    )
    assert "no links" in out
    other = runner.invoke(
        app,
        [
            "gitlab",
            "issue-links",
            "7",
            "-p",
            "PROJ-001",
            "--url",
            "https://gitlab.test/group/other",
        ],
    )
    assert other.exit_code == 1  # no route for it: an explicit not found
    assert "group%2Fother" in served.requests[-1].url
    assert TOKEN not in other.output
