import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.edits.service import EditsError, FetchResult
from qa_workbench.main import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


def test_fetch_uses_the_configured_repository(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    destination = isolated / "edits"
    monkeypatch.setenv("DARK_KNIGHT_EDITS_REPO", "owner/edits")
    monkeypatch.setenv("DARK_KNIGHT_EDITS_REF", "v1")
    monkeypatch.setenv("DARK_KNIGHT_EDITS_DIR", str(destination))
    calls: list[dict[str, object]] = []

    def fake_fetch(**kwargs: object) -> FetchResult:
        calls.append(kwargs)
        return FetchResult(destination=destination, videos=(destination / "a.mp4",))

    monkeypatch.setattr("qa_workbench.edits.cli.fetch_edits", fake_fetch)

    result = runner.invoke(app, ["edits", "fetch"])

    assert result.exit_code == 0
    assert calls[0]["repo"] == "owner/edits"
    assert calls[0]["ref"] == "v1"
    assert calls[0]["destination"] == destination
    assert "Fetched 1 edit(s)" in _plain(result.output)


def test_fetch_options_override_the_configuration(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    destination = isolated / "elsewhere"
    calls: list[dict[str, object]] = []

    def fake_fetch(**kwargs: object) -> FetchResult:
        calls.append(kwargs)
        return FetchResult(destination=destination, videos=())

    monkeypatch.setattr("qa_workbench.edits.cli.fetch_edits", fake_fetch)

    result = runner.invoke(
        app,
        [
            "edits",
            "fetch",
            "--repo",
            "owner/other",
            "--ref",
            "v2",
            "--dir",
            str(destination),
            "--sha256",
            "abc",
        ],
    )

    assert result.exit_code == 0
    assert calls[0]["repo"] == "owner/other"
    assert calls[0]["ref"] == "v2"
    assert calls[0]["destination"] == destination
    assert calls[0]["sha256"] == "abc"


def test_fetch_requires_a_repository(isolated: Path) -> None:
    result = runner.invoke(app, ["edits", "fetch"])

    assert result.exit_code == 1
    assert "No edits repository configured" in _plain(result.output)


def test_fetch_reports_failures(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    monkeypatch.setenv("DARK_KNIGHT_EDITS_REPO", "owner/edits")

    def fake_fetch(**kwargs: object) -> FetchResult:
        raise EditsError("GitHub answered 404.")

    monkeypatch.setattr("qa_workbench.edits.cli.fetch_edits", fake_fetch)

    result = runner.invoke(app, ["edits", "fetch"])

    assert result.exit_code == 1
    assert "GitHub answered 404" in _plain(result.output)


def test_list_shows_the_edits(monkeypatch: pytest.MonkeyPatch, isolated: Path) -> None:
    destination = isolated / "edits"
    destination.mkdir()
    (destination / "b.mp4").write_bytes(b"video")
    (destination / "a.mp4").write_bytes(b"video")
    monkeypatch.setenv("DARK_KNIGHT_EDITS_DIR", str(destination))

    result = runner.invoke(app, ["edits", "list"])

    assert result.exit_code == 0
    output = _plain(result.output)
    assert "2 edit(s)" in output
    assert output.index("a.mp4") < output.index("b.mp4")


def test_list_reports_an_empty_folder(
    monkeypatch: pytest.MonkeyPatch, isolated: Path
) -> None:
    destination = isolated / "edits"
    monkeypatch.setenv("DARK_KNIGHT_EDITS_DIR", str(destination))

    result = runner.invoke(app, ["edits", "list"])

    assert result.exit_code == 0
    assert "No edits in" in _plain(result.output)
