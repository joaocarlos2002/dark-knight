"""The base of every page: what it needs from the app, and how it refreshes."""

from dataclasses import dataclass
from pathlib import Path

from textual.containers import Vertical

from qa_workbench.projects.models import Project
from qa_workbench.storage.repository import MarkdownRepository


@dataclass(frozen=True)
class PageContext:
    """The project and where its data lives."""

    data_dir: Path
    project: Project | None

    def repository(self) -> MarkdownRepository:
        """The project's records. Reads and writes go through this."""
        from qa_workbench.workspace import repository_for

        if self.project is None:
            raise ValueError("No project is open.")
        return repository_for(self.data_dir, self.project)


class Page(Vertical):
    """A page: built from a context, redrawn by :meth:`refresh_data`."""

    can_focus = True

    def __init__(self, context: PageContext, **kwargs) -> None:
        super().__init__(**kwargs)
        self.context = context
        self.add_class("page")

    def on_mount(self) -> None:
        self.refresh_data()

    def focus_primary(self) -> None:
        """Move the keyboard focus into the page, so its shortcuts work."""
        for widget in self.query("*"):
            if widget.focusable and widget.display:
                widget.focus()
                return
        self.focus()  # nothing inside to focus (an empty list): keep the shortcuts

    def refresh_data(self) -> None:  # pragma: no cover - overridden by pages
        """Re-read the records and redraw."""
