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
    result = runner.invoke(app, ["project", *args])
    return result, _plain(result.output)


def test_create_then_list_and_show(isolated_data: Path) -> None:
    created, output = _run(
        "create",
        "Shop",
        "--repository",
        "acme/shop",
        "--environment",
        "staging=https://staging.example.com",
        "--framework",
        "django",
        "--language",
        "python",
        "--command",
        "test=pytest",
    )
    assert created.exit_code == 0
    assert "Created PROJ-001" in output
    assert (isolated_data / "projects" / "PROJ-001" / "project.yaml").is_file()

    listed, output = _run("list")
    assert listed.exit_code == 0
    assert "PROJ-001  active    Shop" in output

    shown, output = _run("show", "PROJ-001")
    assert shown.exit_code == 0
    assert "acme/shop" in output
    assert "staging https://staging.example.com" in output
    assert "test: pytest" in output


def test_list_with_no_projects_explains_how_to_start() -> None:
    result, output = _run("list")

    assert result.exit_code == 0
    assert "No projects yet" in output


def test_archive_hides_the_project_from_the_default_list() -> None:
    _run("create", "Shop")

    archived, output = _run("archive", "PROJ-001")
    assert archived.exit_code == 0
    assert "Archived PROJ-001" in output

    assert "PROJ-001" not in _run("list")[1]
    assert "PROJ-001  archived  Shop" in _run("list", "--all")[1]


def test_archiving_twice_fails_with_a_clear_message() -> None:
    _run("create", "Shop")
    _run("archive", "PROJ-001")

    result, output = _run("archive", "PROJ-001")

    assert result.exit_code == 1
    assert "already archived" in output


def test_unknown_project_fails_with_a_clear_message() -> None:
    result, output = _run("show", "PROJ-404")

    assert result.exit_code == 1
    assert "PROJ-404 was not found" in output


def test_blank_name_is_rejected() -> None:
    result, output = _run("create", "  ")

    assert result.exit_code == 1
    assert "name" in output


@pytest.mark.parametrize("pair", ["staging", "=https://x.example.com", "staging="])
def test_malformed_environment_pairs_are_usage_errors(pair: str) -> None:
    result, output = _run("create", "Shop", "--environment", pair)

    assert result.exit_code == 2
    assert "NAME=VALUE" in output


def test_environment_with_credentials_is_refused() -> None:
    result, output = _run(
        "create", "Shop", "--environment", "staging=https://user:pw@example.com"
    )

    assert result.exit_code == 2
    assert "must not embed credentials" in output


def test_corrupt_project_is_reported_and_fails_the_listing(
    isolated_data: Path,
) -> None:
    _run("create", "Good")
    _run("create", "Bad")
    (isolated_data / "projects" / "PROJ-002" / "project.yaml").write_text(
        "name: [unclosed\n", encoding="utf-8"
    )

    result, output = _run("list")

    assert result.exit_code == 1
    assert "PROJ-001  active    Good" in output
    assert "Warning: Invalid project record" in output


def test_tui_opens_the_requested_project(monkeypatch: pytest.MonkeyPatch) -> None:
    from qa_workbench.tui.app import WorkbenchApp

    _run("create", "Shop")
    opened: list[str] = []
    monkeypatch.setattr(
        WorkbenchApp, "run", lambda self: opened.append(self._project.id)
    )

    result = runner.invoke(app, ["tui", "--project", "PROJ-001"])

    assert result.exit_code == 0
    assert opened == ["PROJ-001"]


def test_tui_refuses_an_unknown_project(monkeypatch: pytest.MonkeyPatch) -> None:
    from qa_workbench.tui.app import WorkbenchApp

    started: list[bool] = []
    monkeypatch.setattr(WorkbenchApp, "run", lambda self: started.append(True))

    result = runner.invoke(app, ["tui", "--project", "PROJ-404"])

    assert result.exit_code == 1
    assert "PROJ-404 was not found" in _plain(result.output)
    assert started == []


def test_tui_applies_shortcut_overrides_from_config(
    monkeypatch: pytest.MonkeyPatch, isolated_data: Path, tmp_path: Path
) -> None:
    from qa_workbench.tui.app import WorkbenchApp

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[shortcuts]\ntoggle_context = "f3"\n', encoding="utf-8"
    )
    keys: list[str] = []
    monkeypatch.setattr(
        WorkbenchApp,
        "run",
        lambda self: keys.append(self._workbench_keymap.key_for("toggle_context")),
    )

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 0
    assert keys == ["f3"]


def test_tui_refuses_conflicting_shortcuts(
    monkeypatch: pytest.MonkeyPatch, isolated_data: Path, tmp_path: Path
) -> None:
    from qa_workbench.tui.app import WorkbenchApp

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[shortcuts]\ntoggle_context = "f1"\n', encoding="utf-8"
    )
    started: list[bool] = []
    monkeypatch.setattr(WorkbenchApp, "run", lambda self: started.append(True))

    result = runner.invoke(app, ["tui"])

    assert result.exit_code == 1
    assert "F1 is assigned to both" in _plain(result.output)
    assert started == []
