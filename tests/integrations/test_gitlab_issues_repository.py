import pytest
from fake_gitlab import PREFIX, FakeGateway, make_client

from qa_workbench.integrations.errors import NotFoundError, UnexpectedResponseError
from qa_workbench.integrations.gitlab.issues import GitLabIssues
from qa_workbench.integrations.gitlab.repository import GitLabRepository

ISSUE = {
    "iid": 7,
    "title": "Login fails",
    "description": "Steps:\n1. open /login",
    "state": "opened",
    "labels": ["bug", "area::auth"],
    "author": {"username": "ada"},
    "web_url": "https://gitlab.test/group/app/-/issues/7",
    "updated_at": "2026-10-01T10:00:00Z",
}
NOTE = {
    "id": 1,
    "author": {"username": "bob"},
    "body": "Reproduced",
    "created_at": "2026-10-01T11:00:00Z",
    "system": False,
}


def _issues(routes):
    gateway = FakeGateway({PREFIX + k: v for k, v in routes.items()})
    return GitLabIssues(make_client(gateway)), gateway


def test_lists_open_issues_filtered_by_labels() -> None:
    issues, gateway = _issues({"/issues": [ISSUE]})

    found = issues.list_issues(labels=("bug", "area::auth"), limit=5)

    assert found[0].iid == 7 and found[0].labels == ("bug", "area::auth")
    params = gateway.requests[0].params
    assert params["state"] == "opened" and params["labels"] == "bug,area::auth"


def test_an_empty_project_is_an_empty_list_not_an_error() -> None:
    issues, _ = _issues({"/issues": []})

    assert issues.list_issues() == []


def test_get_issue_includes_description_labels_and_comments() -> None:
    issues, _ = _issues({"/issues/7": ISSUE, "/issues/7/notes": [NOTE]})

    issue = issues.get_issue(7)

    assert issue.description.startswith("Steps:")
    assert issue.notes[0].author == "bob" and issue.notes[0].body == "Reproduced"


def test_missing_issue_is_not_found() -> None:
    issues, _ = _issues({})

    with pytest.raises(NotFoundError):
        issues.get_issue(99)


def test_malformed_issue_names_what_is_missing() -> None:
    issues, _ = _issues({"/issues": [{"iid": 1}]})

    with pytest.raises(UnexpectedResponseError, match="missing"):
        issues.list_issues()


COMMIT = {
    "id": "abc123",
    "title": "Fix login",
    "author_name": "Ada",
    "committed_date": "2026-10-02T09:00:00Z",
}
MR = {
    "iid": 3,
    "title": "Fix login",
    "state": "opened",
    "source_branch": "fix/login",
    "target_branch": "main",
    "author": {"username": "ada"},
    "web_url": "https://gitlab.test/group/app/-/merge_requests/3",
    "updated_at": "2026-10-02T09:30:00Z",
}


def _repository(routes):
    gateway = FakeGateway({PREFIX + k: v for k, v in routes.items()})
    return GitLabRepository(make_client(gateway)), gateway


def test_lists_commits_for_a_ref_since_a_date() -> None:
    repository, gateway = _repository({"/repository/commits": [COMMIT]})

    commits = repository.list_commits(ref="main", since="2026-10-01", limit=3)

    assert commits[0].sha == "abc123" and commits[0].author == "Ada"
    assert gateway.requests[0].params["ref_name"] == "main"
    assert gateway.requests[0].params["since"] == "2026-10-01"


def test_commit_detail_lists_real_changed_files() -> None:
    repository, _ = _repository(
        {
            "/repository/commits/abc123": COMMIT,
            "/repository/commits/abc123/diff": [
                {"new_path": "src/login.py"},
                {"new_path": "tests/test_login.py"},
            ],
        }
    )

    assert repository.get_commit("abc123").files == (
        "src/login.py",
        "tests/test_login.py",
    )


def test_merge_requests_list_and_detail_with_files() -> None:
    repository, _ = _repository(
        {
            "/merge_requests": [MR],
            "/merge_requests/3": MR,
            "/merge_requests/3/diffs": [{"new_path": "src/login.py"}],
        }
    )

    assert repository.list_merge_requests()[0].source_branch == "fix/login"
    assert repository.get_merge_request(3).files == ("src/login.py",)


def test_diff_without_a_path_is_reported() -> None:
    repository, _ = _repository(
        {"/merge_requests/3": MR, "/merge_requests/3/diffs": [{"old": "x"}]}
    )

    with pytest.raises(UnexpectedResponseError, match="diff is missing"):
        repository.get_merge_request(3)
