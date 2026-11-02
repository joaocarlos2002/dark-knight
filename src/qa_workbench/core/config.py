"""Cross-platform application configuration."""

import sys
import tomllib
from dataclasses import dataclass, field
from os import environ
from pathlib import Path

from qa_workbench.i18n import (
    ENGLISH,
    ENVIRONMENT_VARIABLE,
    UnknownLanguageError,
    normalize,
    stored_language,
)


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


def _project_root() -> Path:
    """Return the repository root for a source checkout."""
    return Path(__file__).resolve().parents[3]


def _default_edits_dir() -> Path:
    """Return the project's `assets/batman-edits` folder."""
    root = _project_root()
    if (root / "assets").is_dir():
        return root / "assets" / "batman-edits"
    return Path.cwd() / "assets" / "batman-edits"


def _resolve_edits_dir(value: object) -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = _project_root() / path
    return path


def _as_bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ConfigurationError(f"{name} must be true or false.")


@dataclass(frozen=True)
class AppConfig:
    """Resolved global configuration for one application run."""

    config_dir: Path
    data_dir: Path
    log_level: str = "INFO"
    log_file: Path | None = None
    shortcuts: dict[str, str] = field(default_factory=dict)
    splash_enabled: bool = True
    edits_dir: Path = field(default_factory=_default_edits_dir)
    splash_player: str | None = None
    edits_repo: str | None = None
    edits_ref: str | None = None
    edits_sha256: str | None = None
    language: str = ENGLISH

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
        document: dict[str, object] = {}
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

        shortcuts = document.get("shortcuts", {})
        if not isinstance(shortcuts, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in shortcuts.items()
        ):
            raise ConfigurationError(
                f"The [shortcuts] section in {config_file} must map action names "
                "to key strings."
            )

        startup = document.get("startup", {})
        if not isinstance(startup, dict):
            raise ConfigurationError(
                f"The [startup] section in {config_file} must be a table."
            )
        splash_enabled = _as_bool(
            environ.get("DARK_KNIGHT_SPLASH", startup.get("splash", True)),
            "splash",
        )
        configured_edits_dir = environ.get(
            "DARK_KNIGHT_EDITS_DIR", startup.get("edits_dir")
        )
        edits_dir = (
            _resolve_edits_dir(configured_edits_dir)
            if configured_edits_dir
            else _default_edits_dir()
        )
        configured_player = environ.get(
            "DARK_KNIGHT_SPLASH_PLAYER", startup.get("player")
        )
        splash_player = str(configured_player) if configured_player else None
        configured_repo = environ.get("DARK_KNIGHT_EDITS_REPO", startup.get("repo"))
        edits_repo = str(configured_repo).strip() if configured_repo else None
        configured_ref = environ.get("DARK_KNIGHT_EDITS_REF", startup.get("ref"))
        edits_ref = str(configured_ref).strip() if configured_ref else None
        configured_sha256 = environ.get(
            "DARK_KNIGHT_EDITS_SHA256", startup.get("sha256")
        )
        edits_sha256 = (
            str(configured_sha256).strip().lower() if configured_sha256 else None
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
        configured_log_file = environ.get(
            "DARK_KNIGHT_LOG_FILE", values.get("log_file")
        )
        log_file = (
            Path(str(configured_log_file)).expanduser() if configured_log_file else None
        )
        try:
            language = (
                normalize(environ[ENVIRONMENT_VARIABLE])
                if environ.get(ENVIRONMENT_VARIABLE)
                else stored_language(config_dir) or ENGLISH
            )
        except UnknownLanguageError as error:
            raise ConfigurationError(f"{ENVIRONMENT_VARIABLE}: {error}") from error
        return cls(
            config_dir=config_dir,
            data_dir=data_dir,
            log_level=log_level,
            log_file=log_file,
            shortcuts=dict(shortcuts),
            splash_enabled=splash_enabled,
            edits_dir=edits_dir,
            splash_player=splash_player,
            edits_repo=edits_repo,
            edits_ref=edits_ref,
            edits_sha256=edits_sha256,
            language=language,
        )
