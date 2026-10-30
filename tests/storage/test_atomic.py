from pathlib import Path

import pytest

from qa_workbench.storage.atomic import write_text_atomic


def test_writes_utf8_text_without_converting_line_endings(tmp_path: Path) -> None:
    target = tmp_path / "note.md"

    write_text_atomic(target, "olá\r\nmundo\n".replace("\r\n", "\n"))

    assert target.read_bytes() == "olá\nmundo\n".encode()


def test_replaces_an_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "note.md"
    target.write_text("old", encoding="utf-8")

    write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "new"


def test_failure_keeps_the_original_and_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "note.md"
    target.write_text("original", encoding="utf-8")

    def broken_replace(source: str, destination: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("qa_workbench.storage.atomic.os.replace", broken_replace)

    with pytest.raises(OSError, match="disk full"):
        write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "original"
    assert [p.name for p in tmp_path.iterdir()] == ["note.md"]
