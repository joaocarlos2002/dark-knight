"""API tokens kept by the application, outside any project.

A token is stored by the name of the environment variable that would otherwise
carry it (``GITLAB_TOKEN``, ``NVIDIA_API_KEY``), so every integration that reads
its token from the environment finds a stored one without a change. The
environment always wins, so scripts and CI behave as before.

The file lives in the user's configuration directory, never in a project, a
record, an export, or the repository, and is created readable by its owner only
(where the operating system supports it). A token is never printed, logged,
audited, or put in an error message.
"""

import json
import os
import re
import tempfile
from collections.abc import Iterator, Mapping
from pathlib import Path

FILE_NAME = "credentials.json"
# Friendly names for the services the workbench knows about.
SERVICES = {
    "gitlab": "GITLAB_TOKEN",
    "nvidia": "NVIDIA_API_KEY",
    "opencode": "OPENCODE_SERVER_PASSWORD",
}
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_MAX_LENGTH = 4096


class CredentialError(ValueError):
    """A credential or the credentials file is not usable."""


def variable_for(name: str) -> str:
    """The environment variable name for a service name or a variable name."""
    key = name.strip()
    if key.lower() in SERVICES:
        return SERVICES[key.lower()]
    if _NAME.match(key.upper()):
        return key.upper()
    raise CredentialError(
        f"{name!r} is not a service ({', '.join(SERVICES)}) or an environment "
        "variable name such as MY_SERVICE_TOKEN."
    )


class CredentialStore:
    def __init__(self, directory: Path) -> None:
        self.path = directory / FILE_NAME

    def _read(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise CredentialError(
                f"The credentials file {self.path} cannot be read "
                f"({type(error).__name__}). Fix or remove it."
            ) from error
        if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            raise CredentialError(
                f"The credentials file {self.path} is not a map of names to values."
            )
        return data

    def _write(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # mkstemp creates the file owner-only; replace keeps that mode.
        handle, temporary = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            os.replace(temporary, self.path)
        except OSError as error:
            Path(temporary).unlink(missing_ok=True)
            raise CredentialError(
                f"Could not save the credentials ({type(error).__name__})."
            ) from error

    def names(self) -> list[str]:
        return sorted(self._read())

    def get(self, name: str) -> str | None:
        return self._read().get(variable_for(name))

    def set(self, name: str, value: str) -> str:
        """Store a value and return the variable name it is kept under."""
        variable = variable_for(name)
        value = value.strip()
        if not value:
            raise CredentialError("The value is empty.")
        if "\n" in value or "\r" in value:
            raise CredentialError("The value must be a single line.")
        if len(value) > _MAX_LENGTH:
            raise CredentialError(f"The value is longer than {_MAX_LENGTH} characters.")
        data = self._read()
        data[variable] = value
        self._write(data)
        return variable

    def remove(self, name: str) -> bool:
        variable = variable_for(name)
        data = self._read()
        if variable not in data:
            return False
        del data[variable]
        self._write(data)
        return True


class StoredEnvironment(Mapping[str, str]):
    """The process environment, with stored credentials behind it."""

    def __init__(
        self,
        store: CredentialStore | None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._store = store
        self._environment = os.environ if environment is None else environment

    def _stored(self) -> dict[str, str]:
        return self._store._read() if self._store is not None else {}

    def __getitem__(self, key: str) -> str:
        if self._environment.get(key):
            return self._environment[key]
        return self._stored()[key]

    def __iter__(self) -> Iterator[str]:
        yield from {*self._environment, *self._stored()}

    def __len__(self) -> int:
        return len(set(self._environment) | set(self._stored()))

    def source_of(self, name: str) -> str | None:
        """``environment``, ``stored``, or ``None``. Never the value."""
        variable = variable_for(name)
        if self._environment.get(variable):
            return "environment"
        return "stored" if variable in self._stored() else None


def token_report(store: CredentialStore | None) -> list[tuple[str, str | None]]:
    """Each known service's variable and where its token comes from
    (``environment``, ``stored``, or ``None``). Never a value."""
    environment = StoredEnvironment(store)
    names = dict.fromkeys(
        [*SERVICES.values(), *(store.names() if store is not None else [])]
    )
    return [(name, environment.source_of(name)) for name in names]


def default_store() -> CredentialStore | None:
    """The store in the user's configuration directory, or ``None`` if there is
    no usable configuration (the environment still works)."""
    from qa_workbench.core.config import AppConfig, ConfigurationError

    try:
        return CredentialStore(AppConfig.load().config_dir)
    except ConfigurationError:
        return None


def default_environment() -> StoredEnvironment:
    return StoredEnvironment(default_store())
