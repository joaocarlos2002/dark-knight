import re
from pathlib import Path

import pytest
from fake_gitlab import PREFIX, FakeGateway
from typer.testing import CliRunner

from qa_workbench.integrations.gitlab import cli
from qa_workbench.main import app

runner = CliRunner()
SECRET = "glpat-not-a-real-token-123456"


def _plain(text: str) -> str:
    return re.sub(r"\[[0-9;]*m", "", text)


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    return tmp_path / "config"


def test_a_stored_token_lets_gitlab_commands_run_without_exporting_it(
    config, monkeypatch, tmp_path
) -> None:
    gateway = FakeGateway({PREFIX + "/issues": []})
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    url = "https://gitlab.test/group/app"
    assert (
        runner.invoke(app, ["project", "create", "Demo", "--repository", url]).exit_code
        == 0
    )
    allow = [
        "security",
        "set",
        "-p",
        "PROJ-001",
        "--allow-host",
        "gitlab.test",
        "--by",
        "Ana",
    ]
    assert runner.invoke(app, allow).exit_code == 0

    missing = runner.invoke(app, ["gitlab", "issues", "-p", "PROJ-001"])
    assert missing.exit_code == 1 and "config token set" in _plain(missing.output)
    assert gateway.requests == []

    runner.invoke(app, ["config", "token", "set", "gitlab", "--stdin"], input=SECRET)
    result = runner.invoke(app, ["gitlab", "issues", "-p", "PROJ-001"])

    assert result.exit_code == 0, result.output
    assert gateway.requests[0].headers["PRIVATE-TOKEN"] == SECRET
    assert SECRET not in result.output
    audit_files = [p for p in (tmp_path / "data").rglob("audit.jsonl")]
    assert audit_files and all(
        SECRET not in p.read_text(encoding="utf-8") for p in audit_files
    )
