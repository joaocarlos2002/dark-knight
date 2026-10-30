import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app

runner = CliRunner()

SOURCE = """## Users can log in

Priority: high

Acceptance criteria:
- Reaches the dashboard.

## Users can log out
"""


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "login.md"
    path.write_text(SOURCE, encoding="utf-8")
    return path


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


def _project() -> None:
    result, _ = _run("project", "create", "Demo")
    assert result.exit_code == 0


def test_import_creates_requirements_in_the_project(
    isolated_data: Path, source: Path
) -> None:
    _project()

    result, output = _run("requirements", "import", str(source), "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "Created REQ-001  Users can log in" in output
    assert "2 created, 0 skipped, 0 with problems." in output
    folder = isolated_data / "projects" / "PROJ-001" / "requirements"
    assert (folder / "REQ-001.md").is_file()
    assert (folder / "REQ-002.md").is_file()


def test_list_shows_status_priority_and_title(source: Path) -> None:
    _project()
    _run("requirements", "import", str(source), "-p", "PROJ-001")

    result, output = _run("requirements", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "REQ-001  draft       high    Users can log in" in output
    assert "REQ-002  draft       -       Users can log out" in output


def test_list_without_requirements_explains_how_to_start() -> None:
    _project()

    result, output = _run("requirements", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "No requirements yet" in output


def test_coverage_flags_uncovered_requirements(source: Path) -> None:
    _project()
    _run("requirements", "import", str(source), "-p", "PROJ-001")

    result, output = _run("requirements", "coverage", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "REQ-001  UNCOVERED  Users can log in  [no test cases]" in output
    assert "0 of 2 requirements covered." in output


def test_importing_twice_skips_what_is_already_there(source: Path) -> None:
    _project()
    _run("requirements", "import", str(source), "-p", "PROJ-001")

    result, output = _run("requirements", "import", str(source), "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "Skipped REQ-001 (already imported from this file)" in output
    assert "0 created, 2 skipped, 0 with problems." in output


def test_author_and_version_are_stored(isolated_data: Path, source: Path) -> None:
    _project()

    _run(
        "requirements",
        "import",
        str(source),
        "-p",
        "PROJ-001",
        "--author",
        "Bruno",
        "--source-version",
        "v2",
    )

    text = (
        isolated_data / "projects" / "PROJ-001" / "requirements" / "REQ-001.md"
    ).read_text(encoding="utf-8")
    assert "author: Bruno" in text
    assert "source_version: v2" in text
    assert "source: login.md" in text


def test_problems_are_reported_and_the_exit_code_is_one(tmp_path: Path) -> None:
    _project()
    path = tmp_path / "mixed.md"
    path.write_text("## Bad\n\nPriority: urgent\n\n## Good\n", encoding="utf-8")

    result, output = _run("requirements", "import", str(path), "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "Created REQ-001  Good" in output
    assert "Problem mixed.md:1: priority 'urgent' is not understood" in output
    assert "1 created, 0 skipped, 1 with problems." in output


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("missing.md", None, "is not a file"),
        ("doc.pdf", b"%PDF", "unsupported file type '.pdf'"),
        ("empty.md", b"", "is empty"),
    ],
)
def test_unreadable_sources_fail_with_a_clear_message(
    tmp_path: Path, name: str, content: bytes | None, message: str
) -> None:
    _project()
    path = tmp_path / name
    if content is not None:
        path.write_bytes(content)

    result, output = _run("requirements", "import", str(path), "-p", "PROJ-001")

    assert result.exit_code == 1
    assert message in output


def test_an_unknown_project_is_reported(source: Path) -> None:
    result, output = _run("requirements", "import", str(source), "-p", "PROJ-404")

    assert result.exit_code == 1
    assert "PROJ-404 was not found" in output


def test_an_archived_project_cannot_receive_requirements(source: Path) -> None:
    _project()
    _run("project", "archive", "PROJ-001")

    result, output = _run("requirements", "import", str(source), "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "PROJ-001 is archived and cannot be changed" in output


def test_an_archived_project_can_still_be_read(source: Path) -> None:
    _project()
    _run("requirements", "import", str(source), "-p", "PROJ-001")
    _run("project", "archive", "PROJ-001")

    result, output = _run("requirements", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "REQ-001" in output


def test_a_damaged_requirement_is_a_warning_and_an_error_exit(
    isolated_data: Path, source: Path
) -> None:
    _project()
    _run("requirements", "import", str(source), "-p", "PROJ-001")
    damaged = isolated_data / "projects" / "PROJ-001" / "requirements" / "REQ-002.md"
    damaged.write_text("not a record", encoding="utf-8")

    result, output = _run("requirements", "list", "-p", "PROJ-001")

    assert result.exit_code == 1
    assert "REQ-001" in output
    assert "Warning: Invalid Markdown record" in output
