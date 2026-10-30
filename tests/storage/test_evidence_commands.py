import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


@pytest.fixture(autouse=True)
def project(isolated_data: Path) -> None:
    assert _run("project", "create", "Demo")[0].exit_code == 0


@pytest.fixture
def shot(tmp_path: Path) -> Path:
    path = tmp_path / "login.png"
    path.write_bytes(b"png bytes")
    return path


def _add(shot: Path, *extra: str):
    return _run(
        "evidence",
        "add",
        str(shot),
        "-p",
        "PROJ-001",
        "--source",
        "manual",
        "--description",
        "Login page",
        *extra,
    )


def test_add_copies_the_file_and_shows_the_hash(
    isolated_data: Path, shot: Path
) -> None:
    result, output = _add(shot)

    assert result.exit_code == 0
    assert "Registered EVD-001  sha256 " in output
    folder = isolated_data / "projects" / "PROJ-001" / "evidence" / "files" / "EVD-001"
    assert (folder / "login.png").read_bytes() == b"png bytes"
    assert shot.read_bytes() == b"png bytes"


def test_list_shows_hash_type_and_description(shot: Path) -> None:
    _add(shot)

    result, output = _run("evidence", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "EVD-001" in output and "image/png" in output and "Login page" in output


def test_an_annotated_copy_points_at_the_original(shot: Path, tmp_path: Path) -> None:
    _add(shot)
    annotated = tmp_path / "annotated.png"
    annotated.write_bytes(b"png bytes + arrow")

    result, output = _add(annotated, "--derived-from", "EVD-001")

    assert result.exit_code == 0
    assert "Registered EVD-002" in output


def test_verify_passes_for_intact_evidence(shot: Path) -> None:
    _add(shot)

    result, output = _run("evidence", "verify", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "All evidence is intact." in output


def test_verify_finds_a_modified_file(isolated_data: Path, shot: Path) -> None:
    _add(shot)
    stored = (
        isolated_data
        / "projects"
        / "PROJ-001"
        / "evidence"
        / "files"
        / "EVD-001"
        / "login.png"
    )
    stored.write_bytes(b"tampered")

    all_result, all_output = _run("evidence", "verify", "-p", "PROJ-001")
    one_result, one_output = _run("evidence", "verify", "EVD-001", "-p", "PROJ-001")

    assert all_result.exit_code == 1
    assert (
        "EVD-001: the file content does not match its recorded SHA-256." in all_output
    )
    assert one_result.exit_code == 1
    assert "SHA-256" in one_output


def test_empty_projects_say_how_to_start() -> None:
    result, output = _run("evidence", "list", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "No evidence yet" in output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--source-url", "ftp://x.test"], "source_url must be an http(s) URL"),
        (["--derived-from", "EVD-099"], "EVD-099 was not found"),
    ],
)
def test_invalid_input_is_refused(shot: Path, args: list[str], message: str) -> None:
    result, output = _add(shot, *args)

    assert result.exit_code == 1
    assert message in output


def test_a_missing_file_is_refused(tmp_path: Path) -> None:
    result, output = _add(tmp_path / "missing.png")

    assert result.exit_code == 1
    assert "is not a file" in output
