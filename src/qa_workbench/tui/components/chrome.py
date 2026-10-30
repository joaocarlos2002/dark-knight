"""Application header and footer."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from qa_workbench.tui import identity


class AppHeader(Vertical):
    """Corporate identity and the active project.

    The second row is secondary and is hidden on short terminals.
    """

    def __init__(self, project_label: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._project_label = project_label

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-row-1"):
            yield Static(identity.COMPANY, id="header-company")
            yield Static(self._project_label, id="header-project")
        with Horizontal(id="header-row-2"):
            yield Static(identity.DIVISION, id="header-division")
            yield Static(identity.LOCATION, id="header-location")

    def set_project_label(self, label: str) -> None:
        self._project_label = label
        self.query_one("#header-project", Static).update(label)


class AppFooter(Vertical):
    """Corporate status line above the project and shortcut line."""

    def __init__(self, status_line: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._status_line = status_line

    def compose(self) -> ComposeResult:
        yield Static(identity.footer_identity_text(), id="footer-identity")
        yield Static(self._status_line, id="status-bar")

    def set_status_line(self, text: str) -> None:
        self._status_line = text
        self.query_one("#status-bar", Static).update(text)
