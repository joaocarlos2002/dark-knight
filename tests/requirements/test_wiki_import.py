import re
from pathlib import Path

import pytest
from fake_gitlab import TOKEN, FakeGateway
from typer.testing import CliRunner

from qa_workbench.integrations.gitlab import cli
from qa_workbench.integrations.gitlab.wiki import WikiPage
from qa_workbench.main import app
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.requirements.wiki_import import import_wiki_pages
from qa_workbench.storage.repository import MarkdownRepository

BASE = "https://gitlab.test"
SLUG = "Requisitos/GE01/GE01.01-Autorizar"
PAGE = WikiPage(SLUG, "GE01.01 Autorizar", "Texto.\n\n- RN-GE01.01.08 Regra.\n")


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", [REQUIREMENT_SCHEMA])


def _import(repo: MarkdownRepository, *pages: WikiPage):
    return import_wiki_pages(repo, pages, base_url=BASE, group="nees/x")


def test_a_page_becomes_a_draft_requirement_with_its_provenance(repo) -> None:
    report = _import(repo, PAGE)

    record = report.created[0]
    assert (
        record.metadata["status"] == "draft" and record.metadata["origin"] == "imported"
    )
    assert record.metadata["source_ref"] == SLUG
    assert record.metadata["source_url"].endswith(f"/groups/nees/x/-/wikis/{SLUG}")
    assert len(record.metadata["source_sha256"]) == 64
    assert record.metadata["tags"] == ["GE01", "GE01.01"]
    assert record.metadata["business_rules"] == ["RN-GE01.01.08"]
    assert "Texto." in record.body


def test_importing_again_changes_nothing(repo) -> None:
    _import(repo, PAGE)

    report = _import(repo, PAGE)

    assert not report.created and not report.updated and len(report.skipped) == 1
    assert len(repo.list_records("REQ").records) == 1


def test_a_changed_page_updates_the_record_and_goes_back_to_draft(repo) -> None:
    first = _import(repo, PAGE).created[0]
    repo.update(first.id, {"status": "in_review"})

    report = _import(repo, WikiPage(SLUG, "GE01.01 Autorizar", "Texto novo.\n"))

    assert not report.created and len(report.updated) == 1
    record = repo.get(first.id)
    assert record.metadata["status"] == "draft" and "Texto novo." in record.body
    assert len(repo.list_records("REQ").records) == 1


def test_an_empty_page_is_reported_not_imported(repo) -> None:
    report = _import(repo, WikiPage("Requisitos/vazio", "Vazio", "  \n"))

    assert not report.created and report.issues[0].location == "Requisitos/vazio"


# -- the command -----------------------------------------------------------------


def test_import_wiki_command_end_to_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
    gateway = FakeGateway(
        {
            "/api/v4/groups/group/wikis": [
                {
                    "slug": SLUG,
                    "title": PAGE.title,
                    "format": "markdown",
                    "content": PAGE.content,
                }
            ]
        }
    )
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    runner = CliRunner()
    runner.invoke(
        app,
        ["project", "create", "Demo", "--repository", "https://gitlab.test/group/app"],
    )
    allow = [
        "security",
        "set",
        "-p",
        "PROJ-001",
        "--allow-host",
        "gitlab.test",
        "--by",
        "A",
    ]
    runner.invoke(app, allow)

    first = runner.invoke(app, ["requirements", "import-wiki", "-p", "PROJ-001"])
    out = re.sub(r"\x1b\[[0-9;]*m", "", first.output)
    assert first.exit_code == 0, out
    assert "Created REQ-001" in out and "1 created, 0 updated" in out

    again = runner.invoke(app, ["requirements", "import-wiki", "-p", "PROJ-001"])
    assert "0 created, 0 updated, 1 unchanged" in again.output
    assert TOKEN not in first.output + again.output
