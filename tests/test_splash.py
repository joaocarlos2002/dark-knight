import random
import subprocess
from pathlib import Path

import pytest

from qa_workbench.core import splash
from qa_workbench.core.config import AppConfig


def _config(tmp_path: Path, **overrides: object) -> AppConfig:
    values: dict[str, object] = {
        "config_dir": tmp_path / "config",
        "data_dir": tmp_path / "data",
    }
    values.update(overrides)
    return AppConfig(**values)  # type: ignore[arg-type]


def _edits(directory: Path, *names: str) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = directory / name
        path.write_bytes(b"video")
        paths.append(path)
    return paths


def test_find_edits_keeps_only_video_files(tmp_path: Path) -> None:
    directory = tmp_path / "edits"
    _edits(directory, "b.MP4", "a.mkv", "notes.txt")
    (directory / "nested").mkdir()

    assert splash.find_edits(directory) == [
        directory / "a.mkv",
        directory / "b.MP4",
    ]


def test_find_edits_returns_empty_for_a_missing_directory(tmp_path: Path) -> None:
    assert splash.find_edits(tmp_path / "missing") == []


def test_choose_edit_returns_none_without_edits() -> None:
    assert splash.choose_edit([]) is None


def test_choose_edit_picks_one_of_the_edits(tmp_path: Path) -> None:
    edits = _edits(tmp_path, "a.mp4", "b.mp4", "c.mp4")

    chosen = splash.choose_edit(edits, random.Random(4))

    assert chosen in edits


def test_player_command_uses_ffplay_flags() -> None:
    command = splash.player_command("ffplay", Path("edit.mp4"))

    assert command[0] == "ffplay"
    assert "-fs" in command
    assert "-autoexit" in command
    assert "-noborder" in command
    assert "-exitonkeydown" in command
    assert command[-1] == "edit.mp4"


def test_player_command_uses_mpv_flags() -> None:
    command = splash.player_command("/usr/bin/mpv", Path("edit.mp4"))

    assert command[0] == "/usr/bin/mpv"
    assert "--fullscreen" in command
    assert "--no-osc" in command
    assert command[-1] == "edit.mp4"


def test_player_command_uses_vlc_flags() -> None:
    command = splash.player_command("vlc", Path("edit.mp4"))

    assert "--fullscreen" in command
    assert "--play-and-exit" in command
    assert command[-1] == "edit.mp4"


def test_splash_is_skipped_when_disabled(tmp_path: Path) -> None:
    directory = tmp_path / "edits"
    _edits(directory, "edit.mp4")
    played: list[object] = []

    result = splash.play_startup_splash(
        _config(tmp_path, splash_enabled=False, edits_dir=directory),
        interactive=True,
        runner=played.append,
    )

    assert result is None
    assert played == []


def test_splash_is_skipped_without_a_terminal(tmp_path: Path) -> None:
    directory = tmp_path / "edits"
    _edits(directory, "edit.mp4")
    played: list[object] = []

    result = splash.play_startup_splash(
        _config(tmp_path, edits_dir=directory),
        interactive=False,
        runner=played.append,
    )

    assert result is None
    assert played == []


def test_splash_is_skipped_without_edits(tmp_path: Path) -> None:
    played: list[object] = []

    result = splash.play_startup_splash(
        _config(tmp_path, edits_dir=tmp_path / "missing"),
        interactive=True,
        runner=played.append,
    )

    assert result is None
    assert played == []


def test_splash_is_skipped_without_a_player(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "edits"
    _edits(directory, "edit.mp4")
    monkeypatch.setattr(splash.shutil, "which", lambda name: None)
    played: list[object] = []

    result = splash.play_startup_splash(
        _config(tmp_path, edits_dir=directory),
        interactive=True,
        runner=played.append,
    )

    assert result is None
    assert played == []


def test_splash_plays_a_random_edit_fullscreen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "edits"
    edits = _edits(directory, "edit.mp4")
    calls: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setattr(splash, "_hide_terminal", lambda: None)
    monkeypatch.setattr(splash, "_restore_terminal", lambda handle: None)

    def runner(command: list[str], **kwargs: object) -> None:
        calls.append((command, kwargs))

    result = splash.play_startup_splash(
        _config(tmp_path, edits_dir=directory, splash_player="ffplay"),
        interactive=True,
        runner=runner,
    )

    assert result == edits[0]
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[0] == "ffplay"
    assert command[-1] == str(edits[0])
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_splash_failure_still_starts_the_workbench(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "edits"
    _edits(directory, "edit.mp4")
    monkeypatch.setattr(splash, "_hide_terminal", lambda: None)
    monkeypatch.setattr(splash, "_restore_terminal", lambda handle: None)

    def runner(command: list[str], **kwargs: object) -> None:
        raise OSError("player crashed")

    result = splash.play_startup_splash(
        _config(tmp_path, edits_dir=directory, splash_player="ffplay"),
        interactive=True,
        runner=runner,
    )

    assert result is not None


def test_splash_restores_the_terminal_after_playback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "edits"
    _edits(directory, "edit.mp4")
    restored: list[int | None] = []
    monkeypatch.setattr(splash, "_hide_terminal", lambda: 42)
    monkeypatch.setattr(splash, "_restore_terminal", restored.append)

    splash.play_startup_splash(
        _config(tmp_path, edits_dir=directory, splash_player="ffplay"),
        interactive=True,
        runner=lambda command, **kwargs: None,
    )

    assert restored == [42]
