"""Textual application shell: navigation, content, context, and status bar."""

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.ports import BrowserMode
from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.core.config import AppConfig
from qa_workbench.projects.models import Project
from qa_workbench.tui import identity, navigation
from qa_workbench.tui.commands import WorkbenchCommands
from qa_workbench.tui.components.browser_preview import BrowserPreview
from qa_workbench.tui.components.chrome import AppFooter, AppHeader
from qa_workbench.tui.keymap import Keymap
from qa_workbench.tui.layout import ShellLayout, WidthClass, layout_for
from qa_workbench.tui.palette import PaletteEntry, destination_key, palette_entries
from qa_workbench.tui.status import Status, format_status
from qa_workbench.tui.theme import SHELL_CSS


def _status_bar_text(project: Project | None, keymap: Keymap) -> str:
    label = project.id if project else identity.NO_PROJECT_FOOTER
    return f"{label} │ {keymap.help_bar()}"


def _header_project_text(project: Project | None) -> str:
    if project is None:
        return identity.NO_PROJECT_HEADER
    return f"{project.id} / {project.name.upper()}"


def _context_text(project: Project | None) -> str:
    if project is None:
        return "CONTEXT\n\nProject  none\nEnvironment  -\nRepository  -"
    environments = ", ".join(e.name for e in project.environments) or "-"
    return (
        "CONTEXT\n\n"
        f"Project  {project.name}\n"
        f"Environment  {environments}\n"
        f"Repository  {project.repository or '-'}"
    )


class WorkbenchApp(App[None]):
    """Three-area shell shared by every workbench screen."""

    TITLE = "QA WORKBENCH"
    CSS = SHELL_CSS
    COMMANDS = {WorkbenchCommands}

    def __init__(
        self,
        project: Project | None = None,
        keymap: Keymap | None = None,
        preview_channel: PreviewChannel | None = None,
    ) -> None:
        self._workbench_keymap = keymap or Keymap.default()
        # Read by Textual while it builds its default bindings.
        self.COMMAND_PALETTE_BINDING = self._workbench_keymap.key_for("command_palette")
        super().__init__()
        for shortcut in self._workbench_keymap.shortcuts:
            if shortcut.action != "command_palette":
                self.bind(shortcut.key, shortcut.action, description=shortcut.label)
        self._project = project
        self._preview_channel = preview_channel or PreviewChannel(
            AppConfig.load().data_dir / "browser-preview"
        )
        self._shell_layout: ShellLayout | None = None
        self._sidebar_visible = True
        self._context_visible = True
        self._current = navigation.find_item(navigation.DEFAULT_KEY)

    def compose(self) -> ComposeResult:
        yield AppHeader(_header_project_text(self._project), id="header")
        with Horizontal(id="body"):
            with Vertical(id="navigation"):
                yield Static(identity.brand_text(), id="brand")
                yield OptionList(*self._sidebar_options(), id="sidebar")
            with Vertical(id="main"):
                yield Static(id="page-title")
                yield Static(id="page-body")
                yield BrowserPreview(self._preview_channel, id="browser-preview")
            yield Static(_context_text(self._project), id="context")
        yield AppFooter(
            _status_bar_text(self._project, self._workbench_keymap), id="footer"
        )

    def on_mount(self) -> None:
        self.query_one("#browser-preview").display = False
        self._show_page(self._current)
        self._apply_layout(self.size.width, self.size.height)
        self.query_one("#sidebar", OptionList).focus()

    def on_resize(self, event: Resize) -> None:
        self._apply_layout(event.size.width, event.size.height)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is None:
            return
        self.navigate(event.option.id)

    def navigate(self, key: str) -> None:
        """Open a destination and keep the sidebar highlight in sync."""
        self._current = navigation.find_item(key)
        self._show_page(self._current)
        sidebar = self.query_one("#sidebar", OptionList)
        sidebar.highlighted = sidebar.get_option_index(key)
        if self._is_narrow():
            self._sidebar_visible = False
            self._refresh_regions()

    def palette_entries(self) -> list[PaletteEntry]:
        return palette_entries(self._workbench_keymap)

    async def run_palette_action(self, action: str) -> None:
        destination = destination_key(action)
        if destination is not None:
            self.navigate(destination)
        else:
            await self.run_action(action)

    def action_toggle_sidebar(self) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self._refresh_regions()

    def action_toggle_context(self) -> None:
        self._context_visible = not self._context_visible
        self._refresh_regions()

    def action_toggle_browser_preview(self) -> None:
        """Show or hide the preview. The browser itself is never affected."""
        panel = self.query_one("#browser-preview", BrowserPreview)
        panel.display = not panel.display
        if panel.display:
            panel.refresh_preview(force=True)

    def action_cycle_browser_mode(self) -> None:
        """Ask the running browser for its next mode (applied between actions)."""
        modes = [mode.value for mode in BrowserMode]
        try:
            state = self._preview_channel.read()
            requested = self._preview_channel.read_control().get("mode")
            current = str(
                requested or (state.mode if state else BrowserMode.PREVIEW.value)
            )
            wanted = modes[(modes.index(current) + 1) % len(modes)]
            self._preview_channel.request(mode=wanted)
        except (BrowserError, OSError) as error:
            self.notify(f"Could not change the mode: {error}", severity="error")
            return
        note = (
            " (visible needs a restart: it applies to the next run)"
            if (
                wanted == BrowserMode.VISIBLE.value
                or current == BrowserMode.VISIBLE.value
            )
            else ""
        )
        self.notify(f"Browser mode requested: {wanted}{note}")

    def action_toggle_browser_pause(self) -> None:
        try:
            state = self._preview_channel.read()
            if state is None or state.execution_state != "running":
                self.notify("No browser is running.", severity="warning")
                return
            self._preview_channel.request(paused=not state.paused)
        except (BrowserError, OSError) as error:
            self.notify(f"Could not pause or resume: {error}", severity="error")
            return
        self.notify("Resume requested." if state.paused else "Pause requested.")

    def action_help(self) -> None:
        self.notify(
            self._workbench_keymap.help_text(), title="Keyboard shortcuts", timeout=15
        )

    def action_focus_search(self) -> None:
        fields = self.screen.query(".searchable")
        if not fields:
            self.notify("This page has no search field.", severity="warning")
            return
        fields.first().focus()

    def action_go_back(self) -> None:
        """Close the topmost overlay: the narrow menu, then the context drawer."""
        if self._is_narrow() and self._sidebar_visible:
            self._sidebar_visible = False
        elif self._shell_layout is not None and (
            self._shell_layout.width_class is not WidthClass.WIDE
            and self._context_visible
        ):
            self._context_visible = False
        else:
            return
        self._refresh_regions()

    def _is_narrow(self) -> bool:
        return (
            self._shell_layout is not None
            and self._shell_layout.width_class is WidthClass.NARROW
        )

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
        narrow = self._is_narrow()
        self.query_one("#navigation").display = self._sidebar_visible
        self.query_one("#context").display = self._context_visible
        # A narrow menu takes the whole width, so content steps aside.
        self.query_one("#main").display = not (narrow and self._sidebar_visible)

    def _show_page(self, item: navigation.NavItem) -> None:
        self.query_one("#page-title", Static).update(item.title.upper())
        if item.key == "browser-preview":
            self.query_one("#page-body", Static).update(
                "Follow the browser Playwright is driving. Ctrl+B shows or hides it."
            )
            panel = self.query_one("#browser-preview", BrowserPreview)
            panel.display = True
            panel.refresh_preview(force=True)
            return
        self.query_one("#page-body", Static).update(
            f"{format_status(Status.PENDING)}  This module is not available yet."
        )

    @staticmethod
    def _sidebar_options() -> list[Option]:
        options: list[Option] = []
        for section in navigation.SECTIONS:
            options.append(Option(section.title.upper(), disabled=True))
            options.extend(
                Option(item.title.upper(), id=item.key) for item in section.items
            )
        return options
