"""Smoke test of the *installed* package, run from outside the repository.

CI installs the built wheel into a fresh virtual environment and runs this file
with that environment's Python. It proves that what a user installs has its
modules, its data files, and a working command line and TUI on this operating
system, which the in-repository test suite cannot show.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def fail(message: str) -> None:
    print(f"SMOKE FAILED: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    import qa_workbench

    location = Path(qa_workbench.__file__).resolve()
    if "site-packages" not in location.parts:
        fail(f"qa_workbench was imported from {location}, not from the installed wheel")
    print(f"installed package: {location.parent}")

    data = Path(tempfile.mkdtemp(prefix="dk-smoke-"))
    env = {
        **os.environ,
        "DARK_KNIGHT_DATA_DIR": str(data / "data"),
        "DARK_KNIGHT_CONFIG_DIR": str(data / "config"),
        "PYTHONUTF8": "1",
    }

    def run(*args: str, expect: tuple[int, ...] = (0,)) -> str:
        result = subprocess.run(
            [sys.executable, "-m", "qa_workbench", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=data,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if result.returncode not in expect:
            fail(f"batman {' '.join(args)} exited {result.returncode}:\n{output}")
        return output

    if "Dark Knight QA" not in run("--version"):
        fail("--version did not print the application name")

    # `doctor` exits 1 when Chromium is not installed, which is fine here; an
    # import error or a crash is not.
    doctor = run("doctor", expect=(0, 1))
    if "Browser:" not in doctor:
        fail(f"doctor did not report the browser state:\n{doctor}")

    run("project", "create", "Smoke project", "--repository", "https://example.com/a/b")
    if "PROJ-001" not in run("project", "list"):
        fail("the created project is not listed")
    run("requirements", "coverage", "-p", "PROJ-001")
    run("security", "show", "-p", "PROJ-001")

    asyncio.run(open_the_workbench(data / "data"))
    print("SMOKE OK")


async def open_the_workbench(data_dir: Path) -> None:
    from qa_workbench.projects.repository import ProjectRepository
    from qa_workbench.tui import navigation
    from qa_workbench.tui.app import WorkbenchApp

    project = ProjectRepository(data_dir).open("PROJ-001")
    app = WorkbenchApp(project, data_dir=data_dir)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        for item in navigation.all_items():
            app.navigate(item.key)  # every destination must open without raising
            await pilot.pause()
        app.navigate("overview")
        await pilot.pause()
        if app.project is None or app.project.id != "PROJ-001":
            fail("the workbench did not open on the project")
    print(f"workbench opened and visited {len(navigation.all_items())} pages")


if __name__ == "__main__":
    main()
