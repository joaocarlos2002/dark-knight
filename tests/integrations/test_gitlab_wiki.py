import re
from pathlib import Path
from urllib.parse import quote

import pytest
from fake_gitlab import TOKEN, FakeGateway, answer, make_client
from typer.testing import CliRunner

from qa_workbench.integrations.errors import NotFoundError
from qa_workbench.integrations.gitlab import cli
from qa_workbench.integrations.gitlab.wiki import (
    GitLabWiki,
    business_rules,
    group_of,
    page_url,
    requirement_codes,
)
from qa_workbench.main import app

runner = CliRunner()
GROUP = "/api/v4/groups/group/wikis"
SLUG = "Requisitos/GE01/GE01.01-Autorizar-assistente-escolar"
PAGES = [
    {
        "slug": SLUG,
        "title": "GE01.01 Autorizar assistente escolar",
        "format": "markdown",
    },
    {"slug": "Requisitos/S02-Sessão", "title": "S02 Sessão", "format": "markdown"},
    {"slug": "Outros/Notas", "title": "Notas", "format": "markdown"},
]
CONTENT = (
    "# GE01.01\n\nO gestor autoriza o assistente.\n\n"
    "- RN-GE01.01.08 O assistente só vê a própria escola.\n"
)


def _wiki(gateway: FakeGateway) -> GitLabWiki:
    return GitLabWiki(make_client(gateway), "group")


def test_list_keeps_only_the_prefix_and_asks_for_content_only_when_wanted() -> None:
    gateway = FakeGateway({GROUP: PAGES})
    wiki = _wiki(gateway)

    pages = wiki.list_pages("Requisitos/")
    assert [p.slug for p in pages] == [SLUG, "Requisitos/S02-Sessão"]
    assert "with_content" not in gateway.requests[0].params

    wiki.list_pages("Requisitos/", with_content=True)
    assert gateway.requests[1].params["with_content"] == "1"


def test_search_needs_every_word_in_the_title_or_slug() -> None:
    wiki = _wiki(FakeGateway({GROUP: PAGES}))

    assert [p.title for p in wiki.search("assistente autorizar")] == [PAGES[0]["title"]]
    assert wiki.search("inexistente") == []


def test_get_page_encodes_slashes_and_accents() -> None:
    slug = "Requisitos/S02-Sessão"
    route = f"{GROUP}/{quote(slug, safe='')}"
    gateway = FakeGateway({route: {**PAGES[1], "content": CONTENT}})

    page = _wiki(gateway).get_page(slug)

    assert page.content == CONTENT and page.title == "S02 Sessão"
    assert "%2F" in gateway.requests[0].url and "%C3%A3" in gateway.requests[0].url


def test_a_missing_page_is_an_explicit_not_found() -> None:
    with pytest.raises(NotFoundError):
        _wiki(FakeGateway({})).get_page("Requisitos/nao-existe")


def test_codes_and_rules_are_told_apart() -> None:
    text = "GE01.01 e S02 usam RN-GE01.01.08 e RN-GE01.01.09"

    assert business_rules(text) == ["RN-GE01.01.08", "RN-GE01.01.09"]
    assert requirement_codes(text) == ["GE01.01", "S02"]
    assert requirement_codes("sem codigo") == []


def test_group_and_page_url() -> None:
    assert group_of("nees/primeira-infancia/ted-14716") == "nees/primeira-infancia"
    assert group_of("alone") == ""
    assert (
        page_url("https://g.test/", "nees/x", "Requisitos/S02-Sessão")
        == "https://g.test/groups/nees/x/-/wikis/Requisitos/S02-Sess%C3%A3o"
    )


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
            GROUP: lambda r: answer(
                [{**p, "content": CONTENT} for p in PAGES]
                if r.params.get("with_content")
                else PAGES
            ),
            f"{GROUP}/{quote(SLUG, safe='')}": {**PAGES[0], "content": CONTENT},
        }
    )
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    created = runner.invoke(
        app,
        ["project", "create", "Demo", "--repository", "https://gitlab.test/group/app"],
    )
    assert created.exit_code == 0, created.output
    allow = ["security", "set", "-p", "PROJ-001", "--allow-host", "gitlab.test"]
    assert runner.invoke(app, [*allow, "--by", "Ana"]).exit_code == 0
    return gateway


def test_wiki_command_lists_searches_and_shows_untrusted_text(served) -> None:
    listing = _plain(runner.invoke(app, ["gitlab", "wiki", "-p", "PROJ-001"]).output)
    assert SLUG in listing and "Outros/Notas" not in listing

    found = _plain(
        runner.invoke(app, ["gitlab", "wiki", "sess", "-p", "PROJ-001"]).output
    )
    assert "S02-Sessão" in found and "GE01" not in found

    shown = _plain(
        runner.invoke(app, ["gitlab", "wiki-page", SLUG, "-p", "PROJ-001"]).output
    )
    assert "UNTRUSTED EXTERNAL DATA" in shown and "RN-GE01.01.08" in shown


def test_the_wiki_is_read_through_the_guard(served, tmp_path) -> None:
    runner.invoke(
        app,
        [
            "security",
            "set",
            "-p",
            "PROJ-001",
            "--remove-host",
            "gitlab.test",
            "--by",
            "Ana",
        ],
    )

    result = runner.invoke(app, ["gitlab", "wiki", "-p", "PROJ-001"])

    assert result.exit_code == 1 and served.requests == []
    assert TOKEN not in result.output
