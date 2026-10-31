"""File dialog: pick a file from a folder tree, so no path has to be typed."""

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DirectoryTree, Static


class FileDialog(ModalScreen["Path | None"]):
    """Dismisses with the chosen file, or ``None`` if cancelled (Escape)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, start: Path | None = None) -> None:
        if not title.strip():
            raise ValueError("FileDialog needs a title.")
        super().__init__()
        self._title = title.strip()
        self._start = start if start is not None and start.is_dir() else Path.home()

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="dialog-title")
            yield Static(
                "Open a folder with Enter, choose a file with Enter, Esc cancels.",
                id="dialog-message",
            )
            yield DirectoryTree(self._start, id="files")

    def on_mount(self) -> None:
        self.query_one(DirectoryTree).focus()

    def choose(self, path: Path) -> None:
        """Pick ``path`` (called when a file is selected in the tree)."""
        self.dismiss(path)

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        event.stop()
        self.choose(Path(event.path))

    def action_cancel(self) -> None:
        self.dismiss(None)
