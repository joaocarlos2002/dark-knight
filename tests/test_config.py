from pathlib import Path

import pytest

from qa_workbench.core.config import AppConfig, ConfigurationError


def test_environment_overrides_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DARK_KNIGHT_LOG_LEVEL", "debug")

    config = AppConfig.load()

    assert config.config_dir == tmp_path / "config"
    assert config.data_dir == tmp_path / "data"
    assert config.log_level == "DEBUG"


def test_invalid_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DARK_KNIGHT_LOG_LEVEL", "verbose")

    with pytest.raises(ConfigurationError, match="must be DEBUG"):
        AppConfig.load()


def test_toml_configuration_is_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[application]\ndata_dir = "~/dark-knight-data"\nlog_level = "WARNING"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    config = AppConfig.load()

    assert config.data_dir == Path.home() / "dark-knight-data"
    assert config.log_level == "WARNING"
