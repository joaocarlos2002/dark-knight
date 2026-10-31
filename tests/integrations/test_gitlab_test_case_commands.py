import re
from pathlib import Path

import pytest
from fake_gitlab import PREFIX, TOKEN, FakeGateway, answer
from typer.testing import CliRunner

from qa_workbench.integrations.gitlab import cli
from qa_workbench.main import app

runner = CliRunner()
URL = "https://gitlab.test/group/app"
ISSUES = PREFIX + "/issues"
CASE = {
    "iid": 7,
    "title": "Autorizar assistente",
    "description": "# Autorizar\n\n## Objetivo\nValidar\n",
    "labels": ["GE01.01", "type::testcase"],
    "web_url": URL + "/-/issues/7",
    "state": "opened",
}


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeGateway:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
    gateway = FakeGateway({ISSUES: [CASE], ISSUES + "/7": CASE})
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    runner.invoke(app, ["project", "create", "Demo", "--repository", URL])
    allow = ["security", "set", "-p", "PROJ-001", "--allow-host", "gitlab.test"]
    assert runner.invoke(app, [*allow, "--by", "Ana"]).exit_code == 0
    return gateway


def test_test_cases_are_listed_by_label_and_shown_as_untrusted_text(served) -> None:
    listing = _plain(
        runner.invoke(app, ["gitlab", "test-cases", "GE01.01", "-p", "PROJ-001"]).output
    )
    assert "#7" in listing and "Autorizar assistente" in listing
    request = served.requests[0]
    assert request.params["issue_type"] == "test_case"
    assert request.params["labels"] == "GE01.01"

    shown = _plain(
        runner.invoke(app, ["gitlab", "test-case", "7", "-p", "PROJ-001"]).output
    )
    assert "UNTRUSTED EXTERNAL DATA" in shown and "Validar" in shown


def test_push_asks_for_approval_then_creates_and_then_does_nothing(served) -> None:
    runner.invoke(
        app,
        [
            "cases",
            "create",
            "Autorizar assistente",
            "-p",
            "PROJ-001",
            "--objective",
            "Validar",
            "--step",
            "Abrir => Abre",
            "--expected-result",
            "Ok",
        ],
    )
    served.routes[ISSUES] = lambda r: answer(CASE, 201) if r.body else answer([])
    push = ["cases", "push", "TC-001", "-p", "PROJ-001", "--by", "Ana"]

    first = runner.invoke(app, push)
    assert first.exit_code == 1 and "APR-" in first.output
    assert not [r for r in served.requests if r.body]  # nothing was written

    request_id = re.search(r"APR-[0-9a-f]+", first.output).group(0)
    decided = ["security", "approve", request_id, "-p", "PROJ-001", "--by", "Bea"]
    assert runner.invoke(app, decided).exit_code == 0

    second = runner.invoke(app, push)
    assert second.exit_code == 0, second.output
    assert "created #7" in _plain(second.output) and TOKEN not in second.output

    third = runner.invoke(app, push)
    assert "unchanged #7" in _plain(third.output)
    assert len([r for r in served.requests if r.body]) == 1
