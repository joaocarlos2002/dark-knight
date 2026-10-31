"""The files a release depends on must agree (see RELEASING.md)."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_version_is_semantic() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", _version())


def test_version_matches_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["version"] == _version()


def test_changelog_has_an_unreleased_section_and_an_entry_for_the_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert re.search(r"^## \[Unreleased\]", changelog, re.M)
    assert re.search(rf"^## \[{re.escape(_version())}\]", changelog, re.M)


def test_the_release_guide_names_the_files_the_workflow_checks() -> None:
    guide = (ROOT / "RELEASING.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    for name in ("VERSION", "pyproject.toml", "CHANGELOG.md"):
        assert name in guide and name in workflow
