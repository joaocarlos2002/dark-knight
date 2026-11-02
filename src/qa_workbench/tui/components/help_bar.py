"""HelpBar: contextual keyboard shortcuts display for the current page."""

from typing import Any

from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from qa_workbench.i18n import tr
from qa_workbench.tui.keymap import Keymap, display_key


class HelpBar(Horizontal):
    """A bar showing the shortcuts of the current page.

    The global shortcuts are in the footer, so they are not repeated here.
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
        items = self._compose_items()
        self.display = bool(items)
        if items:
            self.mount(*items)

    def _compose_items(self) -> list[Static]:
        items: list[Static] = []
        for binding in self._page_bindings:
            key_display = display_key(binding.key)
            items.append(
                Static(f"{key_display} {tr(binding.description)}", classes="help-item")
            )

        return items
