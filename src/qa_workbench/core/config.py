"""Cross-platform application configuration."""

from dataclasses import dataclass
from os import environ
from pathlib import Path
import sys
import tomllib


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid."""


def _platform_config_dir() -> Path:
    if sys.platform == "win32":
        return Path(environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def _platform_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _path_from_env(name: str, default: Path) -> Path:
    value = environ.get(name)
    return Path(value).expanduser() if value else default


@dataclass(frozen=True)
class AppConfig:
    """Resolved global configuration for one application run."""

    config_dir: Path
    data_dir: Path
    log_level: str = "INFO"
    log_file: Path | None = None

    def __post_init__(self) -> None:
        if self.log_level.upper() not in {
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            raise ConfigurationError(
                "log_level must be DEBUG, INFO, WARNING, ERROR, or CRITICAL."
            )

    @classmethod
    def load(cls) -> "AppConfig":
        """Load TOML configuration and apply environment overrides."""
        config_dir = _path_from_env(
            "DARK_KNIGHT_CONFIG_DIR",
            _platform_config_dir() / "dark-knight-qa",
        )
        values: dict[str, object] = {}
        config_file = config_dir / "config.toml"
        if config_file.is_file():
            try:
                with config_file.open("rb") as stream:
                    document = tomllib.load(stream)
            except tomllib.TOMLDecodeError as error:
                raise ConfigurationError(
                    f"Invalid TOML configuration in {config_file}: {error}"
                ) from error
            values = document.get("application", {})
            if not isinstance(values, dict):
                raise ConfigurationError(
                    f"The [application] section in {config_file} must be a table."
                )

        data_dir = _path_from_env(
            "DARK_KNIGHT_DATA_DIR",
            Path(
                str(values.get("data_dir", _platform_data_dir() / "dark-knight-qa"))
            ).expanduser(),
        )
        log_level = str(
            environ.get("DARK_KNIGHT_LOG_LEVEL", values.get("log_level", "INFO"))
        ).upper()
        configured_log_file = environ.get("DARK_KNIGHT_LOG_FILE", values.get("log_file"))
        log_file = (
            Path(str(configured_log_file)).expanduser()
            if configured_log_file
            else None
        )
        return cls(
            config_dir=config_dir,
            data_dir=data_dir,
            log_level=log_level,
            log_file=log_file,
        )
