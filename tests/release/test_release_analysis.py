import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayRequest, GatewayResponse
from qa_workbench.integrations.models import Commit, MergeRequest
from qa_workbench.main import app
from qa_workbench.release.analysis import (
    analyze_release,
    area_of,
    is_test_path,
    words_of,
)
from qa_workbench.release.records import RELEASE_SCHEMA, render, save_analysis
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.suites.schema import SUITE_SCHEMA
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA


class FakeSource:
    def __init__(self, commits: list[Commit], mrs: list[MergeRequest] | None = None):
        self.commits = {c.sha: c for c in commits}
        self.mrs = {m.iid: m for m in mrs or []}

    def list_commits(self, *, ref=None, since=None, limit=20):
        return [Commit(c.sha, c.title, c.author, c.date) for c in self.commits.values()]

    def get_commit(self, sha):
        return self.commits[sha]

    def list_merge_requests(self, *, state="opened", limit=20):
        return list(self.mrs.values())

    def get_merge_request(self, iid):
        return self.mrs[iid]


def _commit(sha: str, title: str, *files: str) -> Commit:
    return Commit(sha, title, "Ada", "2026-10-01", tuple(files))


@pytest.fixture
def repository(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(
        tmp_path / "p", [TEST_CASE_SCHEMA, SUITE_SCHEMA, RELEASE_SCHEMA]
    )


def _case(repository, title: str, **extra):
    fields = {
        "title": title,
        "objective": extra.pop("objective", "Check it"),
        "priority": "high",
        "type": "functional",
        "origin": "manual",
        "status": "active",
        "steps": [{"action": "Do it", "expected": "It works"}],
        "expected_result": "It works",
        **extra,
    }
    return repository.create("TC", fields, f"# {title}\n")


def _suite(repository, title: str, suite_type: str, cases=()):
    fields = {"title": title, "status": "active", "type": suite_type}
    if cases:
        fields["cases"] = list(cases)
    return repository.create("SUITE", fields, f"# {title}\n")


def test_path_helpers() -> None:
    assert area_of("src/auth/login.py") == "src/auth"
    assert area_of("README.md") == "README.md"
    assert is_test_path("tests/test_login.py") and is_test_path("web/a.spec.ts")
    assert not is_test_path("src/auth/login.py")
    assert words_of("src/auth/LoginForm.tsx") == {"auth", "login", "form"}


def test_sensitive_untested_change_is_high_risk_with_real_commits_and_files(
    repository,
) -> None:
    source = FakeSource(
        [
            _commit("a" * 40, "Change login flow", "src/auth/login.py"),
            _commit("b" * 40, "Tweak docs", "docs/guide.md"),
        ]
    )

    analysis = analyze_release(source, repository, ref="main")

    auth = next(a for a in analysis.areas if a.area == "src/auth")
    assert auth.level == "high"
    assert any("sensitive names: auth, login" in r for r in auth.reasons)
    assert any("no test change" in r for r in auth.reasons)
    assert auth.commits == ("a" * 40,) and auth.files == ("src/auth/login.py",)
    assert next(a for a in analysis.areas if a.area == "docs").level == "medium"
    assert analysis.risk_level == "high" and analysis.scope == "ref main"
    assert analysis.files == {
        "src/auth/login.py": ["a" * 40],
        "docs/guide.md": ["b" * 40],
    }
    assert "Full regression recommended" in analysis.regression


def test_changing_tests_with_the_code_lowers_the_risk(repository) -> None:
    source = FakeSource(
        [_commit("c" * 40, "Fix cart", "src/cart/total.py", "tests/cart/test_total.py")]
    )

    analysis = analyze_release(source, repository)

    cart = next(a for a in analysis.areas if a.area == "src/cart")
    assert cart.level == "low" and cart.reasons == ()
    assert "Smoke suite is enough" in analysis.regression


def test_churn_and_wide_commits_are_called_out(repository) -> None:
    commits = [
        _commit(f"{i}" * 40, f"edit {i}", "src/core/engine.py") for i in range(3)
    ]
    commits.append(_commit("9" * 40, "Big", *[f"src/big/f{n}.py" for n in range(21)]))

    analysis = analyze_release(FakeSource(commits), repository)

    core = next(a for a in analysis.areas if a.area == "src/core")
    assert any("changed in 3 or more commits" in r for r in core.reasons)
    big = next(a for a in analysis.areas if a.area == "src/big")
    assert any("more than 20 files" in r for r in big.reasons)


def test_impacted_cases_and_suites_are_matched_and_explained(repository) -> None:
    login = _case(repository, "User can log in", tags=["auth"])
    _case(repository, "Report export to PDF")
    _case(repository, "Old login", status="deprecated", tags=["login"])
    login_suite = _suite(repository, "Auth suite", "functional", [login.id])
    smoke = _suite(repository, "Smoke", "smoke")
    regression = _suite(repository, "Full regression", "regression")
    _suite(repository, "Unrelated", "functional")
    source = FakeSource([_commit("a" * 40, "Auth", "src/auth/login.py")])

    analysis = analyze_release(source, repository)

    assert [c.case_id for c in analysis.impacted_cases] == [login.id]
    assert analysis.impacted_cases[0].matched == ("auth",)
    advice = {s.suite_id: s.why for s in analysis.suites}
    assert "impacted case" in advice[login_suite.id]
    assert "smoke" in advice[smoke.id] and "high-risk" in advice[regression.id]
    assert len(advice) == 3


def test_no_matching_case_is_said_to_be_a_possible_coverage_gap(repository) -> None:
    analysis = analyze_release(
        FakeSource([_commit("a" * 40, "x", "src/billing/invoice.py")]), repository
    )

    assert analysis.impacted_cases == ()
    assert any("coverage may be missing" in line for line in analysis.justification)


def test_empty_scope_and_missing_file_lists_are_stated_as_limitations(
    repository,
) -> None:
    empty = analyze_release(FakeSource([]), repository)
    nofiles = analyze_release(FakeSource([_commit("a" * 40, "x")]), repository)

    assert any("No commits were found" in x for x in empty.limitations)
    assert any("no changed files" in x for x in nofiles.limitations)
    assert empty.risk_level == "low"


def test_merge_requests_are_included_and_can_be_skipped(repository) -> None:
    mr = MergeRequest(
        3, "Fix auth", "merged", "fix/auth", "main", "ada", "u", "t", ("a.py",)
    )
    source = FakeSource([_commit("a" * 40, "x", "src/a/b.py")], [mr])

    assert analyze_release(source, repository).merge_requests[0].iid == 3
    assert (
        analyze_release(source, repository, merge_requests=False).merge_requests == ()
    )


def test_saved_record_is_sealed_and_cites_commits_and_files(repository) -> None:
    case = _case(repository, "User can log in", tags=["auth"])
    source = FakeSource([_commit("a" * 40, "Change login", "src/auth/login.py")])
    analysis = analyze_release(source, repository)

    record = save_analysis(repository, analysis)

    assert record.metadata["risk_level"] == "high"
    assert record.metadata["commits"] == ["a" * 40]
    body = render(analysis)
    for expected in (
        "`aaaaaaaaaa`",
        "`src/auth/login.py`",
        f"[[{case.id}]]",
        "## Limitations",
    ):
        assert expected in body
    from qa_workbench.storage.errors import RecordFinalizedError

    with pytest.raises(RecordFinalizedError):
        repository.update(record.id, {"risk_level": "low"})


# -- command ------------------------------------------------------------------

runner = CliRunner()
URL = "https://gitlab.test/group/app"
P = "/api/v4/projects/group%2Fapp"


class Gateway:
    """Serves the few GitLab routes the analysis reads."""

    def get(self, request: GatewayRequest) -> GatewayResponse:
        import json

        path = request.url.removeprefix("https://gitlab.test")
        routes = {
            P + "/repository/commits": [
                {"id": "a" * 40, "title": "Change login", "author_name": "Ada",
                 "committed_date": "2026-10-01"}
            ],
            P + "/repository/commits/" + "a" * 40: {
                "id": "a" * 40, "title": "Change login", "author_name": "Ada",
                "committed_date": "2026-10-01",
            },
            P + "/repository/commits/" + "a" * 40 + "/diff": [
                {"new_path": "src/auth/login.py"}
            ],
            P + "/merge_requests": [],
        }  # fmt: skip
        if path not in routes:
            return GatewayResponse(404, {}, b"{}")
        return GatewayResponse(200, {}, json.dumps(routes[path]).encode())


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_command_reads_gitlab_through_the_guard_and_saves(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("GITLAB_TOKEN", "glpat-test-token-0123456789")
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: Gateway())
    run = lambda *a: (lambda r: (r, _plain(r.output)))(runner.invoke(app, list(a)))  # noqa: E731
    run("project", "create", "Demo", "--repository", URL)

    asked, out = run("release", "analyze", "-p", "PROJ-001")
    assert asked.exit_code == 1 and "needs approval" in out  # host not authorized yet
    run(
        "security",
        "set",
        "-p",
        "PROJ-001",
        "--allow-host",
        "gitlab.test",
        "--by",
        "Ana",
    )

    done, out = run("release", "analyze", "-p", "PROJ-001", "--ref", "main")
    assert done.exit_code == 0, out
    assert "Saved REL-001: risk high." in out and "src/auth" in out
    assert "high" in run("release", "list", "-p", "PROJ-001")[1]
    assert (
        "`src/auth/login.py`" in run("release", "show", "REL-001", "-p", "PROJ-001")[1]
    )
