"""The interface language (#157).

English is the source language: ``tr("Save")`` returns the text it is given and,
in another language, that language's translation of it. A text with no
translation is shown in English, never as a key or an empty string. Record
content and ids (``REQ-001``), the product name, and anything an AI or an
external system wrote are not translated and do not go through here.

The language is chosen with ``DARK_KNIGHT_LANGUAGE`` or kept by the application
(``batman config language set``, or the language list on the Settings page).
"""

from pathlib import Path

from qa_workbench.i18n.pt_br import PT_BR

ENGLISH = "en"
BRAZILIAN_PORTUGUESE = "pt-BR"

# (code, name in its own language)
LANGUAGES: tuple[tuple[str, str], ...] = (
    (ENGLISH, "English"),
    (BRAZILIAN_PORTUGUESE, "Português (Brasil)"),
)
CATALOGS: dict[str, dict[str, str]] = {ENGLISH: {}, BRAZILIAN_PORTUGUESE: PT_BR}
ENVIRONMENT_VARIABLE = "DARK_KNIGHT_LANGUAGE"
STORED_FILE = "language"

_current = ENGLISH


class UnknownLanguageError(ValueError):
    """The language is not one the application is translated into."""


def normalize(value: str) -> str:
    """The code of a language, accepting any letter case and ``_`` for ``-``."""
    wanted = value.strip().replace("_", "-").lower()
    for code, _name in LANGUAGES:
        if code.lower() == wanted:
            return code
    known = ", ".join(code for code, _name in LANGUAGES)
    raise UnknownLanguageError(
        f"Unknown language {value!r}. The interface is available in: {known}."
    )


def language() -> str:
    return _current


def set_language(value: str) -> str:
    """Use a language from now on and return its code."""
    global _current
    _current = normalize(value)
    return _current


def tr(text: str, /, **values: object) -> str:
    """``text`` in the current language; ``{name}`` fields are filled from
    ``values`` after translating, so a translation may reorder them."""
    shown = CATALOGS[_current].get(text, text)
    return shown.format(**values) if values else shown


def stored_language(config_dir: Path) -> str | None:
    """The language kept by the application, if any and if it is still valid."""
    try:
        return normalize((config_dir / STORED_FILE).read_text(encoding="utf-8"))
    except (OSError, UnknownLanguageError):
        return None


def store_language(config_dir: Path, value: str) -> str:
    """Keep a language for the next runs and return its code."""
    code = normalize(value)
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / STORED_FILE).write_text(code + "\n", encoding="utf-8")
    return code
