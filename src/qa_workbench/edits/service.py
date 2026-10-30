"""Fetch the startup edits from a GitHub repository.

The workbench keeps the videos out of its own history. When a repository is
configured, ``batman edits fetch`` (and the first launch, if the folder is
empty) downloads a tagged archive and copies its video files into the edits
folder. Failures are explicit and never block the workbench.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from qa_workbench.core.config import AppConfig

logger = logging.getLogger(__name__)

VIDEO_SUFFIXES = {".avi", ".gif", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
TOKEN_VARIABLES = ("DARK_KNIGHT_EDITS_TOKEN", "GITHUB_TOKEN")
ARCHIVE_TIMEOUT = 60.0

Downloader = Callable[[str, dict[str, str], float], bytes]


class EditsError(RuntimeError):
    """Raised when the startup edits cannot be fetched or verified."""


@dataclass(frozen=True)
class FetchResult:
    """The videos written by one fetch."""

    destination: Path
    videos: tuple[Path, ...]

    @property
    def count(self) -> int:
        return len(self.videos)


def find_edits(directory: Path) -> list[Path]:
    """Return the playable edits in *directory*, sorted by name."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    return sorted(
        entry
        for entry in entries
        if entry.is_file() and entry.suffix.lower() in VIDEO_SUFFIXES
    )


def archive_url(repo: str, ref: str | None) -> str:
    """Return the GitHub archive URL for *repo* at *ref*.

    Without a ref the repository's default branch is used.
    """
    cleaned = repo.strip().strip("/")
    if not cleaned or cleaned.count("/") != 1:
        raise EditsError("The edits repository must look like 'owner/name'.")
    target = ref.strip() if ref and ref.strip() else "HEAD"
    return f"https://codeload.github.com/{cleaned}/zip/{target}"


def fetch_edits(
    *,
    repo: str,
    destination: Path,
    ref: str | None = None,
    sha256: str | None = None,
    token: str | None = None,
    downloader: Downloader | None = None,
    timeout: float = ARCHIVE_TIMEOUT,
) -> FetchResult:
    """Download *repo* at *ref* and copy its videos into *destination*."""
    url = archive_url(repo, ref)
    headers = {"Accept": "application/vnd.github+json"}
    credential = token or _token_from_environment()
    if credential:
        headers["Authorization"] = f"Bearer {credential}"

    data = (downloader or _download)(url, headers, timeout)
    if sha256:
        _verify_checksum(data, sha256)
    videos = _extract_videos(data, destination)
    if not videos:
        raise EditsError(
            f"The archive from {repo} has no video files "
            f"({', '.join(sorted(VIDEO_SUFFIXES))})."
        )
    return FetchResult(destination=destination, videos=tuple(videos))


def ensure_edits(
    config: AppConfig, *, downloader: Downloader | None = None
) -> FetchResult | None:
    """Fetch the configured edits when the folder is empty; never raises."""
    if not config.edits_repo or find_edits(config.edits_dir):
        return None
    try:
        return fetch_edits(
            repo=config.edits_repo,
            ref=config.edits_ref,
            destination=config.edits_dir,
            sha256=config.edits_sha256,
            downloader=downloader,
        )
    except EditsError as error:
        logger.warning("Could not fetch the startup edits: %s", error)
        return None


def _token_from_environment() -> str | None:
    for name in TOKEN_VARIABLES:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _download(url: str, headers: dict[str, str], timeout: float) -> bytes:
    try:
        response = httpx.get(
            url, headers=headers, timeout=timeout, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise EditsError(
            f"GitHub answered {error.response.status_code} for {url}."
        ) from error
    except httpx.HTTPError as error:
        raise EditsError(f"Could not download {url}: {error}") from error
    return response.content


def _verify_checksum(data: bytes, expected: str) -> None:
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected.strip().lower():
        raise EditsError(
            f"The archive checksum does not match: expected {expected}, got {actual}."
        )


def _extract_videos(data: bytes, destination: Path) -> list[Path]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise EditsError("The downloaded file is not a valid zip archive.") from error

    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if Path(name).suffix.lower() not in VIDEO_SUFFIXES:
                continue
            target = destination / name
            with archive.open(member) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            written.append(target)
    return sorted(written)
