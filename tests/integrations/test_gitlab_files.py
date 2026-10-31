import base64
import re
from pathlib import Path
from urllib.parse import quote

import pytest
from fake_gitlab import PREFIX, TOKEN, FakeGateway, answer, make_client
from typer.testing import CliRunner

from qa_workbench.integrations.errors import NotFoundError
from qa_workbench.integrations.gitlab import cli
from qa_workbench.integrations.gitlab.files import FileRefused, GitLabFiles
from qa_workbench.main import app

runner = CliRunner()
URL = "https://gitlab.test/group/app"
LOGIN = "src/components/Login.tsx"


def _file(text: bytes, size: int | None = None) -> dict:
    return {
        "file_path": LOGIN,
        "size": len(text) if size is None else size,
        "encoding": "base64",
        "content": base64.b64encode(text).decode(),
    }


def _routes(file_body: dict | None = None) -> dict:
    return {
        PREFIX: {"default_branch": "main"},
        PREFIX + "/repository/branches": [
            {
                "name": "feat/login",
                "default": False,
                "protected": False,
                "commit": {
                    "short_id": "abc12345",
                    "committed_date": "2026-10-30T10:00:00Z",
                },
            },
            {
                "name": "main",
                "default": True,
                "protected": True,
                "commit": {"id": "f" * 40},
            },
        ],
        PREFIX + "/repository/tree": lambda r: answer(
            [
                {"name": "README.md", "type": "blob", "path": "README.md"},
                {"name": "src", "type": "tree", "path": "src"},
                {"name": "Zed.txt", "type": "blob", "path": "Zed.txt"},
            ]
            if "path" not in r.params
            else [{"name": "components", "type": "tree", "path": "src/components"}]
        ),
        PREFIX + f"/repository/files/{quote(LOGIN, safe='')}": file_body
        or _file(b"export const key = 'password=hunter22';\nlogin();\n"),
        PREFIX + "/search": [
            {
                "path": LOGIN,
                "startline": 10,
                "data": "// before\nfunction login() {\n  token=abc123456\n}\n",
            }
        ],
    }


def _files(gateway: FakeGateway) -> GitLabFiles:
    return GitLabFiles(make_client(gateway))


def test_branches_are_newest_first_and_marked() -> None:
    gateway = FakeGateway(_routes())

    branches = _files(gateway).list_branches()

    assert gateway.requests[0].params["sort"] == "updated_desc"
    assert [b.name for b in branches] == ["feat/login", "main"]
    assert branches[0].last_commit == "abc12345" and branches[1].default
    assert branches[1].protected and len(branches[1].last_commit) == 8


def test_the_tree_lists_folders_first_on_the_default_branch() -> None:
    gateway = FakeGateway(_routes())

    entries = _files(gateway).list_tree()

    assert [(e.path, e.kind) for e in entries] == [
        ("src", "dir"),
        ("README.md", "file"),
        ("Zed.txt", "file"),
    ]
    tree = next(r for r in gateway.requests if r.url.endswith("/tree"))
    assert tree.params["ref"] == "main" and "path" not in tree.params
    assert _files(gateway).list_tree("src/", "dev")[0].path == "src/components"


def test_a_file_is_read_with_secrets_masked() -> None:
    found = _files(FakeGateway(_routes())).get_file(LOGIN)

    assert found.ref == "main" and found.path == LOGIN
    assert "hunter22" not in found.text and "login();" in found.text


def test_big_and_binary_files_are_refused_not_truncated() -> None:
    big = FakeGateway(_routes(_file(b"x", size=300_000)))
    with pytest.raises(FileRefused, match="limit is"):
        _files(big).get_file(LOGIN)

    for payload in (b"PNG\x00\x01binary", b"\xff\xfe\xfa"):
        with pytest.raises(FileRefused, match="not a text file"):
            _files(FakeGateway(_routes(_file(payload)))).get_file(LOGIN)


def test_a_missing_path_is_an_explicit_not_found() -> None:
    gateway = FakeGateway({PREFIX: {"default_branch": "main"}})

    with pytest.raises(NotFoundError):
        _files(gateway).get_file("nope.txt")


def test_code_search_gives_the_path_and_the_matching_line_masked() -> None:
    gateway = FakeGateway(_routes())

    matches = _files(gateway).search_code("token", "main")

    assert gateway.requests[0].params == {
        "scope": "blobs",
        "search": "token",
        "ref": "main",
        "per_page": "30",
        "page": "1",
    }
    assert [(m.path, m.line) for m in matches] == [(LOGIN, 12)]
    assert "abc123456" not in matches[0].text


# -- the commands ----------------------------------------------------------------


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeGateway:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
    gateway = FakeGateway(_routes())
    monkeypatch.setattr(cli, "default_gateway", lambda: gateway)
    runner.invoke(app, ["project", "create", "Demo", "--repository", URL])
    allow = ["security", "set", "-p", "PROJ-001", "--allow-host", "gitlab.test"]
    assert runner.invoke(app, [*allow, "--by", "Ana"]).exit_code == 0
    return gateway


def _run(*args: str) -> str:
    return _plain(runner.invoke(app, ["gitlab", *args, "-p", "PROJ-001"]).output)


def test_branches_tree_file_and_code_commands(served) -> None:
    assert "feat/login" in _run("branches") and "default" in _run("branches")
    tree = _run("tree")
    assert "src/" in tree and "README.md" in tree
    shown = _run("file", LOGIN)
    assert "UNTRUSTED EXTERNAL DATA" in shown and "hunter22" not in shown
    code = _run("code", "token")
    assert f"{LOGIN}:12:" in code and "abc123456" not in code


def test_a_refused_file_exits_with_the_reason_and_never_the_token(served) -> None:
    served.routes[PREFIX + f"/repository/files/{quote(LOGIN, safe='')}"] = _file(
        b"x", size=400_000
    )

    result = runner.invoke(app, ["gitlab", "file", LOGIN, "-p", "PROJ-001"])

    assert result.exit_code == 1 and "limit is" in result.output
    assert TOKEN not in result.output


def test_another_repository_is_read_with_url(served) -> None:
    served.routes["/api/v4/projects/other%2Fservice/repository/branches"] = [
        {"name": "main", "default": True, "commit": {"id": "a" * 40}}
    ]

    out = _run("branches", "--url", "https://gitlab.test/other/service")

    assert "main" in out
