from pathlib import Path

import pytest

from qa_workbench.core.config import AppConfig, ConfigurationError


def test_environment_overrides_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_toml_configuration_is_loaded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_invalid_toml_preserves_file_context(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    config_file.write_text("[application\n", encoding="utf-8")
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    with pytest.raises(ConfigurationError, match="Invalid TOML") as error:
        AppConfig.load()

    assert str(config_file) in str(error.value)
    assert error.value.__cause__ is not None


def test_application_section_must_be_a_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("application = 1\n", encoding="utf-8")
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    with pytest.raises(ConfigurationError, match="must be a table"):
        AppConfig.load()


def test_shortcuts_are_loaded_from_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[shortcuts]\ntoggle_context = "f3"\n', encoding="utf-8"
    )
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    assert AppConfig.load().shortcuts == {"toggle_context": "f3"}


def test_shortcuts_must_map_names_to_strings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[shortcuts]\nhelp = 5\n", encoding="utf-8")
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    with pytest.raises(ConfigurationError, match=r"\[shortcuts\] section"):
        AppConfig.load()
