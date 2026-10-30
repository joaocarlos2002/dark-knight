"""Textual application shell: navigation, content, context, and status bar."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from qa_workbench.tui import navigation
from qa_workbench.tui.layout import ShellLayout, WidthClass, layout_for
from qa_workbench.tui.status import Status, format_status
from qa_workbench.tui.theme import SHELL_CSS

_HELP = "F1 menu · F2 context · Enter open · Ctrl+Q quit"


def _status_bar_text() -> str:
    return f"No project │ {format_status(Status.READY)} │ F1 Menu │ F2 Context │ ? Help"


class WorkbenchApp(App[None]):
    """Three-area shell shared by every workbench screen."""

    TITLE = "QA WORKBENCH"
    CSS = SHELL_CSS
    BINDINGS = [
        Binding("f1", "toggle_sidebar", "Menu"),
        Binding("f2", "toggle_context", "Context"),
        Binding("question_mark", "help", "Help"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._shell_layout: ShellLayout | None = None
        self._sidebar_visible = True
        self._context_visible = True
        self._current = navigation.find_item(navigation.DEFAULT_KEY)

    def compose(self) -> ComposeResult:
        yield Static("QA WORKBENCH", id="header")
        with Horizontal(id="body"):
            yield OptionList(*self._sidebar_options(), id="sidebar")
            with Vertical(id="main"):
                yield Static(id="page-title")
                yield Static(id="page-body")
            yield Static(self._context_text(), id="context")
        yield Static(_status_bar_text(), id="status-bar")

    def on_mount(self) -> None:
        self._show_page(self._current)
        self._apply_layout(self.size.width, self.size.height)
        self.query_one("#sidebar", OptionList).focus()

    def on_resize(self, event: Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self._current = navigation.find_item(event.option.id)
        self._show_page(self._current)
        if (
            self._shell_layout is not None
            and self._shell_layout.width_class is WidthClass.NARROW
        ):
            self._sidebar_visible = False
            self._refresh_regions()

    def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self._refresh_regions()

    def action_toggle_context(self) -> None:
        self._context_visible = not self._context_visible
        self._refresh_regions()

    def action_help(self) -> None:
        self.notify(_HELP, title="Shortcuts")

    def _apply_layout(self, columns: int, rows: int) -> None:
        if columns <= 0 or rows <= 0:
            return
        layout = layout_for(columns, rows)
        if (
            self._shell_layout is None
            or layout.width_class is not self._shell_layout.width_class
        ):
            self._sidebar_visible = layout.sidebar_visible
            self._context_visible = layout.context_visible
        self._shell_layout = layout
        screen = self.screen
        for width_class in WidthClass:
            screen.set_class(layout.width_class is width_class, f"-{width_class.value}")
        screen.set_class(layout.short, "-short")
        self._refresh_regions()

    def _refresh_regions(self) -> None:
        narrow = (
            self._shell_layout is not None
            and self._shell_layout.width_class is WidthClass.NARROW
        )
        self.query_one("#sidebar").display = self._sidebar_visible
        self.query_one("#context").display = self._context_visible
        # A narrow menu takes the whole width, so content steps aside.
        self.query_one("#main").display = not (narrow and self._sidebar_visible)

    def _show_page(self, item: navigation.NavItem) -> None:
        self.query_one("#page-title", Static).update(item.title.upper())
        self.query_one("#page-body", Static).update(
            f"{format_status(Status.PENDING)}  This module is not available yet."
        )

    @staticmethod
    def _sidebar_options() -> list[Option]:
        options: list[Option] = []
        for section in navigation.SECTIONS:
            options.append(Option(section.title, disabled=True))
            options.extend(Option(item.title, id=item.key) for item in section.items)
        return options

    @staticmethod
    def _context_text() -> str:
        return "CONTEXT\n\nProject  none\nEnvironment  -\nBranch  -\nAI provider  -"
