"""Command palette entries (pure data, no widgets)."""

from dataclasses import dataclass

from qa_workbench.tui import navigation
from qa_workbench.tui.keymap import Keymap, display_key

GO_PREFIX = "go:"

# Shortcuts that make no sense as palette commands.
_EXCLUDED_ACTIONS = frozenset({"command_palette", "go_back"})


@dataclass(frozen=True)
class PaletteEntry:
    """One command: what to show and what to run.

    ``action`` is either ``go:<destination key>`` or an application action.
    """

    title: str
    help: str
    action: str


def palette_entries(keymap: Keymap) -> list[PaletteEntry]:
    """Every command the palette offers: destinations first, then actions."""
    entries = [
        PaletteEntry(f"Go to {item.title}", section.title.title(), GO_PREFIX + item.key)
        for section in navigation.SECTIONS
        for item in section.items
    ]
    entries.extend(
        PaletteEntry(
            shortcut.description,
            f"Shortcut: {display_key(shortcut.key)}",
            shortcut.action,
        )
        for shortcut in keymap.shortcuts
        if shortcut.action not in _EXCLUDED_ACTIONS
    )
    return entries


def destination_key(action: str) -> str | None:
    """Return the destination key of a ``go:`` action, or ``None``."""
    return action[len(GO_PREFIX) :] if action.startswith(GO_PREFIX) else None
