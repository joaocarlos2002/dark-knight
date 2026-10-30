import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from qa_workbench.core.config import AppConfig
from qa_workbench.edits.service import (
    EditsError,
    archive_url,
    ensure_edits,
    fetch_edits,
)


def _config(tmp_path: Path, **overrides: object) -> AppConfig:
    values: dict[str, object] = {
        "config_dir": tmp_path / "config",
        "data_dir": tmp_path / "data",
    }
    values.update(overrides)
    return AppConfig(**values)  # type: ignore[arg-type]


def _archive(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(f"repo-main/{name}", b"video")
    return buffer.getvalue()


def _download(data: bytes):
    def downloader(url: str, headers: dict[str, str], timeout: float) -> bytes:
        return data

    return downloader


def test_archive_url_uses_the_ref() -> None:
    assert (
        archive_url("owner/edits", "v1")
        == "https://codeload.github.com/owner/edits/zip/v1"
    )
    assert archive_url("owner/edits", None).endswith("/zip/HEAD")


def test_archive_url_rejects_a_malformed_repository() -> None:
    with pytest.raises(EditsError, match="owner/name"):
        archive_url("not-a-repository", None)


def test_fetch_edits_copies_the_videos(tmp_path: Path) -> None:
    destination = tmp_path / "edits"

    result = fetch_edits(
        repo="owner/edits",
        ref="v1",
        destination=destination,
        downloader=_download(_archive("a.mp4", "b.MKV", "notes.txt")),
    )

    assert [video.name for video in result.videos] == ["a.mp4", "b.MKV"]
    assert result.count == 2
    assert (destination / "a.mp4").read_bytes() == b"video"


def test_fetch_edits_accepts_a_matching_checksum(tmp_path: Path) -> None:
    data = _archive("a.mp4")

    result = fetch_edits(
        repo="owner/edits",
        destination=tmp_path / "edits",
        sha256=hashlib.sha256(data).hexdigest(),
        downloader=_download(data),
    )

    assert result.count == 1


def test_fetch_edits_rejects_a_mismatched_checksum(tmp_path: Path) -> None:
    with pytest.raises(EditsError, match="checksum"):
        fetch_edits(
            repo="owner/edits",
            destination=tmp_path / "edits",
            sha256="0" * 64,
            downloader=_download(_archive("a.mp4")),
        )


def test_fetch_edits_rejects_an_archive_without_videos(tmp_path: Path) -> None:
    with pytest.raises(EditsError, match="no video files"):
        fetch_edits(
            repo="owner/edits",
            destination=tmp_path / "edits",
            downloader=_download(_archive("notes.txt")),
        )


def test_fetch_edits_rejects_a_file_that_is_not_a_zip(tmp_path: Path) -> None:
    with pytest.raises(EditsError, match="zip archive"):
        fetch_edits(
            repo="owner/edits",
            destination=tmp_path / "edits",
            downloader=_download(b"not a zip"),
        )


def test_fetch_edits_sends_the_token(tmp_path: Path) -> None:
    seen: dict[str, str] = {}

    def downloader(url: str, headers: dict[str, str], timeout: float) -> bytes:
        seen.update(headers)
        return _archive("a.mp4")

    fetch_edits(
        repo="owner/edits",
        destination=tmp_path / "edits",
        token="secret",
        downloader=downloader,
    )

    assert seen["Authorization"] == "Bearer secret"


def test_ensure_edits_skips_without_a_repository(tmp_path: Path) -> None:
    assert ensure_edits(_config(tmp_path)) is None


def test_ensure_edits_skips_when_videos_exist(tmp_path: Path) -> None:
    destination = tmp_path / "edits"
    destination.mkdir()
    (destination / "a.mp4").write_bytes(b"video")

    def downloader(url: str, headers: dict[str, str], timeout: float) -> bytes:
        raise AssertionError("the downloader must not run")

    config = _config(tmp_path, edits_repo="owner/edits", edits_dir=destination)

    assert ensure_edits(config, downloader=downloader) is None


def test_ensure_edits_fetches_into_an_empty_folder(tmp_path: Path) -> None:
    config = _config(tmp_path, edits_repo="owner/edits", edits_dir=tmp_path / "edits")

    result = ensure_edits(config, downloader=_download(_archive("a.mp4")))

    assert result is not None
    assert result.count == 1
    assert (tmp_path / "edits" / "a.mp4").is_file()


def test_ensure_edits_never_raises_on_failure(tmp_path: Path) -> None:
    def downloader(url: str, headers: dict[str, str], timeout: float) -> bytes:
        raise EditsError("offline")

    config = _config(tmp_path, edits_repo="owner/edits", edits_dir=tmp_path / "edits")

    assert ensure_edits(config, downloader=downloader) is None
