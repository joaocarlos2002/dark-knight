"""Status badge: symbol and name, with a tone color as a secondary cue."""

from typing import Any

from textual.widgets import Static

from qa_workbench.tui.status import Status, format_status, style_for


class StatusBadge(Static):
    """Shows a status as ``<symbol> <LABEL>``, never by color alone."""

    def __init__(self, status: Status, **kwargs: Any) -> None:
        super().__init__(format_status(status), **kwargs)
        self._tone = style_for(status).tone
        self.add_class(f"tone-{self._tone}")
        self.status = status

    def set_status(self, status: Status) -> None:
        """Change the displayed status."""
        self.remove_class(f"tone-{self._tone}")
        self._tone = style_for(status).tone
        self.add_class(f"tone-{self._tone}")
        self.status = status
        self.update(format_status(status))
