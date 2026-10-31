"""HelpBar: contextual keyboard shortcuts display for the current page."""

from typing import Any

from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from qa_workbench.tui.keymap import Keymap, display_key


class HelpBar(Horizontal):
    """A bar showing contextual shortcuts for the current page.

    Combines global shortcuts from the keymap with page-specific BINDINGS.
    """

    def __init__(self, keymap: Keymap, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._keymap = keymap
        self._page_bindings: list[Binding] = []
        self.add_class("help-bar")

    def set_page_bindings(self, bindings: list[Binding]) -> None:
        """Update the page-specific bindings and refresh the display."""
        self._page_bindings = bindings
        self._refresh()

    def _refresh(self) -> None:
        self.remove_children()
        self.mount(*self._compose_items())

    def _compose_items(self) -> list[Static]:
        items: list[Static] = []

        # Global shortcuts (always shown)
        global_actions = ("toggle_sidebar", "toggle_context", "command_palette", "help")
        for shortcut in self._keymap.shortcuts:
            if shortcut.action in global_actions:
                items.append(
                    Static(
                        f"[{shortcut.label}] {shortcut.description}",
                        classes="help-item",
                    )
                )

        # Page-specific shortcuts
        for binding in self._page_bindings:
            key_display = display_key(binding.key)
            items.append(
                Static(f"[{key_display}] {binding.description}", classes="help-item")
            )

        return items
