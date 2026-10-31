import os
import re
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app
from qa_workbench.security.credentials import (
    CredentialError,
    CredentialStore,
    StoredEnvironment,
    variable_for,
)

runner = CliRunner()
SECRET = "glpat-not-a-real-token-123456"


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_service_names_and_variable_names_are_understood() -> None:
    assert variable_for("gitlab") == "GITLAB_TOKEN"
    assert variable_for("NVIDIA") == "NVIDIA_API_KEY"
    assert variable_for("my_service_token") == "MY_SERVICE_TOKEN"
    for bad in ("", "a b", "1TOKEN", "x" * 80, "../etc"):
        with pytest.raises(CredentialError):
            variable_for(bad)


def test_a_stored_token_is_kept_and_can_be_removed(tmp_path) -> None:
    store = CredentialStore(tmp_path / "cfg")

    assert store.set("gitlab", f"  {SECRET}\n") == "GITLAB_TOKEN"
    assert store.get("gitlab") == SECRET
    assert store.names() == ["GITLAB_TOKEN"]
    assert store.remove("gitlab") is True
    assert store.remove("gitlab") is False
    assert store.get("gitlab") is None


def test_bad_values_are_refused(tmp_path) -> None:
    store = CredentialStore(tmp_path)

    for bad in ("", "   ", "two\nlines", "x" * 5000):
        with pytest.raises(CredentialError):
            store.set("gitlab", bad)
    assert store.names() == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_the_file_is_readable_by_its_owner_only(tmp_path) -> None:
    store = CredentialStore(tmp_path)
    store.set("gitlab", SECRET)

    assert (store.path.stat().st_mode & 0o777) == 0o600


def test_the_environment_wins_over_the_stored_value(tmp_path) -> None:
    store = CredentialStore(tmp_path)
    store.set("gitlab", "stored-value")

    both = StoredEnvironment(store, {"GITLAB_TOKEN": "from-env"})
    only_store = StoredEnvironment(store, {})
    nothing = StoredEnvironment(CredentialStore(tmp_path / "other"), {})

    assert both.get("GITLAB_TOKEN") == "from-env"
    assert both.source_of("gitlab") == "environment"
    assert only_store.get("GITLAB_TOKEN") == "stored-value"
    assert only_store.source_of("gitlab") == "stored"
    assert nothing.get("GITLAB_TOKEN", "") == "" and nothing.source_of("gitlab") is None


def test_a_damaged_file_is_an_explicit_error_not_an_empty_store(tmp_path) -> None:
    store = CredentialStore(tmp_path)
    store.path.write_text("{not json", encoding="utf-8")

    with pytest.raises(CredentialError, match="cannot be read"):
        store.names()
    store.path.write_text('["a"]', encoding="utf-8")
    with pytest.raises(CredentialError, match="map of names"):
        store.get("gitlab")


def test_no_temporary_file_is_left_behind(tmp_path) -> None:
    store = CredentialStore(tmp_path)
    store.set("gitlab", SECRET)
    store.set("nvidia", "nvapi-fake")

    assert sorted(p.name for p in tmp_path.iterdir()) == ["credentials.json"]


# -- the commands --------------------------------------------------------------


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    for name in ("GITLAB_TOKEN", "NVIDIA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "config"


def test_set_show_and_remove_never_print_the_value(config) -> None:
    stored = runner.invoke(
        app, ["config", "token", "set", "gitlab", "--stdin"], input=SECRET
    )
    assert stored.exit_code == 0, stored.output
    assert SECRET not in stored.output

    shown = _plain(runner.invoke(app, ["config", "token", "show"]).output)
    assert "GITLAB_TOKEN" in shown and "set (stored)" in shown
    assert "NVIDIA_API_KEY" in shown and "not set" in shown
    assert SECRET not in shown

    removed = runner.invoke(app, ["config", "token", "remove", "gitlab"])
    assert removed.exit_code == 0 and "Removed GITLAB_TOKEN" in removed.output
    assert "not set" in _plain(runner.invoke(app, ["config", "token", "show"]).output)


def test_the_environment_is_reported_as_the_source(config, monkeypatch) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", SECRET)

    shown = _plain(runner.invoke(app, ["config", "token", "show"]).output)

    assert "set (environment)" in shown and SECRET not in shown


def test_set_refuses_an_empty_value_and_a_bad_name(config) -> None:
    empty = runner.invoke(
        app, ["config", "token", "set", "gitlab", "--stdin"], input="\n"
    )
    bad = runner.invoke(
        app, ["config", "token", "set", "no spaces", "--stdin"], input="x"
    )

    assert empty.exit_code == 1 and "empty" in _plain(empty.output)
    assert bad.exit_code == 1 and "environment variable name" in _plain(bad.output)


def test_the_token_is_not_saved_inside_any_project(config, tmp_path) -> None:
    runner.invoke(app, ["project", "create", "Demo"])
    runner.invoke(app, ["config", "token", "set", "gitlab", "--stdin"], input=SECRET)

    leaks = [
        p
        for p in (tmp_path / "data").rglob("*")
        if p.is_file() and SECRET in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert leaks == []
    assert (config / "credentials.json").is_file()
    assert os.path.commonpath([config, tmp_path / "data"]) == str(tmp_path)


def test_doctor_reports_each_service_and_where_its_token_comes_from(
    config, monkeypatch
) -> None:
    from qa_workbench.browser import cli as browser_cli
    from qa_workbench.browser.chromium import BrowserSetup, SetupStatus

    ready = SetupStatus(True, Path("chromium.exe"))
    monkeypatch.setattr(
        browser_cli, "default_setup", lambda: BrowserSetup(lambda: ready)
    )
    runner.invoke(app, ["config", "token", "set", "nvidia", "--stdin"], input=SECRET)
    monkeypatch.setenv("GITLAB_TOKEN", SECRET + "-env")

    result = runner.invoke(app, ["doctor"])
    out = _plain(result.output)

    assert result.exit_code == 0, out
    assert "GITLAB_TOKEN" in out and "set (environment)" in out
    assert "NVIDIA_API_KEY" in out and "set (stored)" in out
    assert "OPENCODE_SERVER_PASSWORD" in out and "not set" in out
    assert SECRET not in out
