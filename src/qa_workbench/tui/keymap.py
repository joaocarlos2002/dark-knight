"""Keyboard shortcuts: one place to define, document, and override them."""

from collections.abc import Mapping
from dataclasses import dataclass

from textual.binding import Binding


class KeymapError(ValueError):
    """Raised when a shortcut configuration is invalid."""


@dataclass(frozen=True)
class Shortcut:
    """One action and the key that triggers it."""

    action: str
    key: str
    description: str
    label: str


_DEFAULTS: tuple[Shortcut, ...] = (
    Shortcut("toggle_sidebar", "f1", "Show or hide the navigation menu", "Menu"),
    Shortcut("toggle_context", "f2", "Show or hide the context panel", "Context"),
    Shortcut("command_palette", "ctrl+p", "Open the command palette", "Palette"),
    Shortcut("focus_search", "ctrl+k", "Go to the search field", "Search"),
    Shortcut(
        "toggle_browser_preview",
        "ctrl+b",
        "Show or hide the browser preview",
        "Browser",
    ),
    Shortcut(
        "cycle_browser_mode",
        "f5",
        "Change the browser mode (headless, preview, visible)",
        "Mode",
    ),
    Shortcut(
        "toggle_browser_pause", "f6", "Pause or resume the running browser", "Pause"
    ),
    Shortcut("go_back", "escape", "Close a dialog or go back one level", "Back"),
    Shortcut("help", "question_mark", "Show the keyboard shortcuts", "Help"),
    Shortcut("quit", "ctrl+q", "Quit the workbench", "Quit"),
)

# Keys the terminal or the shell itself relies on.
_RESERVED = frozenset({"ctrl+c", "ctrl+z", "ctrl+s", "ctrl+d"})

_ALIASES = {"?": "question_mark", "esc": "escape", "return": "enter"}

_DISPLAY = {"question_mark": "?", "escape": "Esc"}


def normalize_key(key: str) -> str:
    """Normalize a user-written key such as ``Ctrl+K`` or ``?``."""
    normalized = key.strip().lower()
    return _ALIASES.get(normalized, normalized)


def display_key(key: str) -> str:
    """Render a key for humans, for example ``ctrl+k`` -> ``Ctrl+K``."""
    if key in _DISPLAY:
        return _DISPLAY[key]
    return "+".join(
        part.capitalize() if len(part) > 2 else part.upper() for part in key.split("+")
    )


@dataclass(frozen=True)
class Keymap:
    """The effective shortcuts for one run."""

    shortcuts: tuple[Shortcut, ...]

    @classmethod
    def default(cls) -> "Keymap":
        return cls(_DEFAULTS)

    @classmethod
    def from_overrides(cls, overrides: Mapping[str, str]) -> "Keymap":
        """Apply ``action -> key`` overrides, rejecting anything ambiguous."""
        known = {shortcut.action for shortcut in _DEFAULTS}
        unknown = sorted(set(overrides) - known)
        if unknown:
            raise KeymapError(
                f"Unknown shortcut action(s): {', '.join(unknown)}. "
                f"Valid actions: {', '.join(sorted(known))}."
            )

        shortcuts: list[Shortcut] = []
        for shortcut in _DEFAULTS:
            key = normalize_key(overrides.get(shortcut.action, shortcut.key))
            if not key:
                raise KeymapError(
                    f"The shortcut for {shortcut.action} cannot be empty."
                )
            if key in _RESERVED:
                raise KeymapError(
                    f"{display_key(key)} is reserved by the terminal and cannot be "
                    f"used for {shortcut.action}."
                )
            shortcuts.append(
                Shortcut(shortcut.action, key, shortcut.description, shortcut.label)
            )

        owners: dict[str, str] = {}
        for shortcut in shortcuts:
            if shortcut.key in owners:
                raise KeymapError(
                    f"{display_key(shortcut.key)} is assigned to both "
                    f"{owners[shortcut.key]} and {shortcut.action}."
                )
            owners[shortcut.key] = shortcut.action
        return cls(tuple(shortcuts))

    def key_for(self, action: str) -> str:
        for shortcut in self.shortcuts:
            if shortcut.action == action:
                return shortcut.key
        raise KeyError(f"Unknown shortcut action: {action!r}.")

    def bindings(self) -> list[Binding]:
        """Textual bindings for every shortcut."""
        return [
            Binding(shortcut.key, shortcut.action, shortcut.label)
            for shortcut in self.shortcuts
        ]

    def help_bar(self) -> str:
        """One-line hint for the status bar."""
        shown = ("toggle_sidebar", "toggle_context", "command_palette", "help")
        parts = []
        for shortcut in self.shortcuts:
            if shortcut.action in shown:
                parts.append(f"{display_key(shortcut.key)} {shortcut.label}")
        return " │ ".join(parts)

    def help_text(self) -> str:
        """Multi-line reference listing every shortcut."""
        width = max(len(display_key(shortcut.key)) for shortcut in self.shortcuts)
        return "\n".join(
            f"{display_key(shortcut.key):<{width}}  {shortcut.description}"
            for shortcut in self.shortcuts
        )
