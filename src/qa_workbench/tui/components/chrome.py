"""Application header and footer."""

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from qa_workbench.tui import identity


class AppHeader(Horizontal):
    """One line: the product on the left, the active project on the right."""

    def __init__(self, project_label: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._project_label = project_label

    def compose(self) -> ComposeResult:
        yield Static(identity.PRODUCT, id="header-product")
        yield Static(self._project_label, id="header-project")

    def set_project_label(self, label: str) -> None:
        self._project_label = label
        self.query_one("#header-project", Static).update(label)


class AppFooter(Vertical):
    """The project and the global shortcuts, on one line."""

    def __init__(self, status_line: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._status_line = status_line

    def compose(self) -> ComposeResult:
        yield Static(self._status_line, id="status-bar")

    def set_status_line(self, text: str) -> None:
        self._status_line = text
        self.query_one("#status-bar", Static).update(text)
