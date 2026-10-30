from pathlib import Path

import pytest

from qa_workbench.core.config import AppConfig, ConfigurationError

ROOT = Path(__file__).resolve().parents[1]


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


def test_startup_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))

    config = AppConfig.load()

    assert config.splash_enabled is True
    assert config.edits_dir == ROOT / "assets" / "batman-edits"
    assert config.splash_player is None


def test_relative_edits_dir_resolves_from_the_project_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[startup]\nedits_dir = "assets/batman-edits"\n', encoding="utf-8"
    )
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    assert AppConfig.load().edits_dir == ROOT / "assets" / "batman-edits"


def test_startup_is_loaded_from_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        "[startup]\n"
        "splash = false\n"
        'edits_dir = "~/clips/batman"\n'
        'player = "C:/tools/mpv.exe"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    config = AppConfig.load()

    assert config.splash_enabled is False
    assert config.edits_dir == Path.home() / "clips" / "batman"
    assert config.splash_player == "C:/tools/mpv.exe"


def test_startup_environment_overrides_toml(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[startup]\nsplash = false\nedits_dir = "~/from-toml"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("DARK_KNIGHT_SPLASH", "yes")
    monkeypatch.setenv("DARK_KNIGHT_EDITS_DIR", "~/from-env")
    monkeypatch.setenv("DARK_KNIGHT_SPLASH_PLAYER", "vlc")

    config = AppConfig.load()

    assert config.splash_enabled is True
    assert config.edits_dir == Path.home() / "from-env"
    assert config.splash_player == "vlc"


def test_invalid_splash_flag_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        '[startup]\nsplash = "sometimes"\n', encoding="utf-8"
    )
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    with pytest.raises(ConfigurationError, match="splash must be true or false"):
        AppConfig.load()


def test_startup_section_must_be_a_table(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("startup = 1\n", encoding="utf-8")
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(config_dir))

    with pytest.raises(ConfigurationError, match=r"\[startup\] section"):
        AppConfig.load()
