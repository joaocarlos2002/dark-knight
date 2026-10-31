"""The CI workflow keeps the checks other things depend on, and covers all platforms."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "repository.yml"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def test_the_linux_checks_keep_the_names_branch_protection_may_require() -> None:
    jobs = _jobs()

    assert jobs["repository"]["name"] == "Repository hygiene"
    quality = jobs["python-quality"]
    assert quality["name"] == "Python quality (${{ matrix.python-version }})"
    assert quality["strategy"]["matrix"]["python-version"] == ["3.12", "3.13", "3.14"]
    assert quality["runs-on"] == "ubuntu-latest"


def test_the_tests_also_run_on_windows_and_macos() -> None:
    job = _jobs()["cross-platform-tests"]

    assert set(job["strategy"]["matrix"]["os"]) == {"windows-latest", "macos-latest"}
    assert job["strategy"]["fail-fast"] is False
    assert any("pytest" in step.get("run", "") for step in job["steps"])


def test_the_wheel_is_installed_and_smoke_tested_on_every_platform() -> None:
    job = _jobs()["clean-install"]
    commands = " ".join(step.get("run", "") for step in job["steps"])

    assert set(job["strategy"]["matrix"]["os"]) == {
        "ubuntu-latest",
        "windows-latest",
        "macos-latest",
    }
    assert "uv build --wheel" in commands
    assert "rm -rf build dist" in commands  # stale build output leaks old modules
    assert "dist/*.whl" in commands
    assert "smoke_installed.py" in commands
    assert (ROOT / ".github" / "scripts" / "smoke_installed.py").is_file()
    # Only the wheel is installed: the repository itself is never installed.
    assert "uv sync" not in commands and "pip install -e" not in commands
