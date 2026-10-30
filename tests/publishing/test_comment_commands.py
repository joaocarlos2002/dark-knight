import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.integrations.gitlab import cli as gitlab_cli
from qa_workbench.integrations.http import GatewayError, GatewayResponse
from qa_workbench.main import app

runner = CliRunner()
URL = "https://gitlab.test/group/app"
TOKEN = "glpat-test-token-0123456789"
NOTES = "/api/v4/projects/group%2Fapp/issues/7/notes"


class Gateway:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.reply = GatewayResponse(201, {}, json.dumps({"id": 321}).encode())
        self.failure: GatewayError | None = None

    def get(self, request):  # pragma: no cover - comments never read
        raise AssertionError("publishing must not read")

    def post(self, request):
        if self.failure:
            raise self.failure
        assert request.url.endswith(NOTES), request.url
        assert request.headers["PRIVATE-TOKEN"] == TOKEN
        self.posts.append(request.body)
        return self.reply


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
    created = runner.invoke(app, ["project", "create", "Demo", "--repository", URL])
    assert created.exit_code == 0, created.output
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    added = runner.invoke(
        app,
        ["evidence", "add", str(shot), "-p", "PROJ-001", "--source", "manual",
         "--description", "login page"],
    )  # fmt: skip
    assert added.exit_code == 0, added.output


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Gateway:
    fake = Gateway()
    monkeypatch.setattr(gitlab_cli, "default_gateway", lambda: fake)
    return fake


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


def _draft(body: str = "QA: login works.", *extra: str):
    return _run(
        "comments", "draft", "7", "-p", "PROJ-001", "--author", "Agent QA",
        "--evidence", "EVD-001", "--body", body, *extra,
    )  # fmt: skip


def test_full_flow_draft_request_approve_publish(gateway: Gateway) -> None:
    result, out = _draft()
    assert result.exit_code == 0 and "COMMENT-001" in out
    assert gateway.posts == []

    result, out = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")
    assert result.exit_code == 1 and "needs approval" in out
    assert gateway.posts == []
    request_id = re.search(r"APR-[0-9a-f]{8}", out).group(0)  # type: ignore[union-attr]
    assert "awaiting_approval" in _run("comments", "list", "-p", "PROJ-001")[1]

    approved = _run("security", "approve", request_id, "-p", "PROJ-001", "--by", "Ana")
    assert approved[0].exit_code == 0

    result, out = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")
    assert result.exit_code == 0, out
    assert "#note_321" in out
    assert gateway.posts == [{"body": "QA: login works.\n"}]
    assert "published" in _run("comments", "list", "-p", "PROJ-001")[1]
    audit = _run("security", "audit", "-p", "PROJ-001")[1]
    assert "comment_published" in audit and "approval_used" in audit
    assert "intact" in _run("security", "audit", "-p", "PROJ-001", "--verify")[1]

    again = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")
    assert again[0].exit_code == 1 and "already published" in again[1]
    assert len(gateway.posts) == 1


def test_draft_refuses_secrets_foreign_links_and_missing_evidence() -> None:
    result, out = _draft("token leaked: password=hunter22 see https://evil.test/x")
    assert result.exit_code == 1
    assert "literal password" in out and "evil.test" in out

    no_evidence = _run(
        "comments", "draft", "7", "-p", "PROJ-001", "--author", "Ana", "--body", "ok"
    )
    assert no_evidence[0].exit_code == 1 and "evidence" in no_evidence[1]
    assert "No comments yet" in _run("comments", "list", "-p", "PROJ-001")[1]


def test_draft_needs_exactly_one_source_for_the_text() -> None:
    result, out = _run(
        "comments", "draft", "7", "-p", "PROJ-001", "--author", "Ana",
        "--evidence", "EVD-001",
    )  # fmt: skip

    assert result.exit_code == 1 and "exactly one of --body or --body-file" in out


def test_body_can_come_from_a_file(tmp_path: Path) -> None:
    text = tmp_path / "comment.md"
    text.write_text("QA: login works.\n", encoding="utf-8")

    result, out = _run(
        "comments", "draft", "7", "-p", "PROJ-001", "--author", "Ana",
        "--evidence", "EVD-001", "--body-file", str(text),
    )  # fmt: skip

    assert result.exit_code == 0, out
    assert (
        "QA: login works."
        in _run("comments", "show", "COMMENT-001", "-p", "PROJ-001")[1]
    )


def _approved_draft() -> None:
    _draft()
    out = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")[1]
    request_id = re.search(r"APR-[0-9a-f]{8}", out).group(0)  # type: ignore[union-attr]
    _run("security", "approve", request_id, "-p", "PROJ-001", "--by", "Ana")


def test_a_server_rejection_exits_nonzero_and_is_recorded(gateway: Gateway) -> None:
    gateway.reply = GatewayResponse(403, {}, b'{"message": "403 Forbidden"}')
    _approved_draft()

    result, out = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")

    assert (
        result.exit_code == 1 and "not allowed" in out and "recorded as failed" in out
    )
    assert "failed" in _run("comments", "list", "-p", "PROJ-001")[1]


def test_a_lost_connection_is_reported_as_unknown(gateway: Gateway) -> None:
    gateway.failure = GatewayError("connection reset")
    _approved_draft()

    result, out = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "may or may not have been applied" in out and "outcome_unknown" in out
    retry = _run("comments", "publish", "COMMENT-001", "-p", "PROJ-001")
    assert retry[0].exit_code == 1 and "may have posted" in retry[1]


def test_unknown_project_and_comment_are_reported() -> None:
    assert _run("comments", "list", "-p", "PROJ-404")[0].exit_code == 1
    assert _run("comments", "show", "COMMENT-009", "-p", "PROJ-001")[0].exit_code == 1
