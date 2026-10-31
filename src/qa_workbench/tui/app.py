"""Textual application shell: navigation, content, context, and status bar."""

from os import environ
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.ports import BrowserMode
from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.i18n import (
    ENVIRONMENT_VARIABLE,
    LANGUAGES,
    UnknownLanguageError,
    language,
    normalize,
    set_language,
    store_language,
    tr,
)
from qa_workbench.projects.errors import ProjectError
from qa_workbench.projects.models import Project
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui import identity, navigation, onboarding
from qa_workbench.tui.commands import WorkbenchCommands
from qa_workbench.tui.components.browser_preview import BrowserPreview
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.chrome import AppFooter, AppHeader
from qa_workbench.tui.components.help_bar import HelpBar
from qa_workbench.tui.keymap import Keymap
from qa_workbench.tui.layout import ShellLayout, WidthClass, layout_for
from qa_workbench.tui.pages import PAGES, Page, PageContext
from qa_workbench.tui.palette import PaletteEntry, destination_key, palette_entries
from qa_workbench.tui.status import Status, format_status
from qa_workbench.tui.theme import SHELL_CSS

BROWSER_HINT = "Follow the browser Playwright is driving. Ctrl+B shows or hides it."
UNAVAILABLE = "This module is not available yet."


def _status_bar_text(project: Project | None, keymap: Keymap) -> str:
    label = project.id if project else tr(identity.NO_PROJECT_FOOTER)
    return f"{label} │ {keymap.help_bar()}"


def _header_project_text(project: Project | None) -> str:
    if project is None:
        return tr(identity.NO_PROJECT_HEADER)
    return f"{project.id} / {project.name.upper()}"


def _context_text(project: Project | None) -> str:
    heading = tr("CONTEXT")
    if project is None:
        return (
            f"{heading}\n\n{tr('Project')}  {tr('none')}\n"
            f"{tr('Environment')}  -\n{tr('Repository')}  -"
        )
    environments = ", ".join(e.name for e in project.environments) or "-"
    return (
        f"{heading}\n\n"
        f"{tr('Project')}  {project.name}\n"
        f"{tr('Environment')}  {environments}\n"
        f"{tr('Repository')}  {project.repository or '-'}"
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
        data_dir: Path | None = None,
        welcome: bool = False,
    ) -> None:
        self._workbench_keymap = keymap or Keymap.default()
        # Read by Textual while it builds its default bindings.
        self.COMMAND_PALETTE_BINDING = self._workbench_keymap.key_for("command_palette")
        super().__init__()
        for shortcut in self._workbench_keymap.shortcuts:
            if shortcut.action != "command_palette":
                self.bind(shortcut.key, shortcut.action, description=shortcut.label)
        self._project = project
        self._welcome = welcome
        self._data_dir = data_dir or AppConfig.load().data_dir
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
                yield OptionList(*self._sidebar_options(), id="sidebar")
            with Vertical(id="main"):
                yield Static(id="page-title")
                yield Static(id="page-body")
                with Vertical(id="page-content"):
                    for key, page_class in PAGES.items():
                        yield page_class(self._page_context(), id=f"page-{key}")
                yield BrowserPreview(self._preview_channel, id="browser-preview")
            yield Static(_context_text(self._project), id="context")
        yield HelpBar(self._workbench_keymap, id="help-bar")
        yield AppFooter(
            _status_bar_text(self._project, self._workbench_keymap), id="footer"
        )

    def on_mount(self) -> None:
        self.query_one("#browser-preview").display = False
        self._show_page(self._current)
        self._apply_layout(self.size.width, self.size.height)
        sidebar = self.query_one("#sidebar", OptionList)
        sidebar.highlighted = sidebar.get_option_index(self._current.key)
        sidebar.focus()
        if (
            self._welcome
            and self._project is None
            and onboarding.needs_welcome(ProjectRepository(self._data_dir))
        ):
            onboarding.start(self)

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
        page = self._page_for(key)
        if page is not None:
            page.focus_primary()
        if self._is_narrow():
            self._sidebar_visible = False
            self._refresh_regions()

    def _page_context(self) -> PageContext:
        return PageContext(self._data_dir, self._project)

    @property
    def project(self) -> Project | None:
        return self._project

    def open_project(self, project_id: str) -> None:
        """Make a project the current one and show its overview."""
        try:
            project = ProjectRepository(self._data_dir).open(project_id)
        except ProjectError as error:
            self.notify(str(error), severity="error", title="Project not opened")
            return
        self._set_project(project)
        self.navigate("overview")
        self.notify(f"{project.id} {project.name} is open.")

    def project_archived(self, project_id: str) -> None:
        """The page archived a project: refresh it if it is the open one."""
        if self._project is not None and self._project.id == project_id:
            self._set_project(ProjectRepository(self._data_dir).open(project_id))

    def _set_project(self, project: Project | None) -> None:
        self._project = project
        self.query_one("#header", AppHeader).set_project_label(
            _header_project_text(project)
        )
        self.query_one("#footer", AppFooter).set_status_line(
            _status_bar_text(project, self._workbench_keymap)
        )
        self.query_one("#context", Static).update(_context_text(project))
        for page in self.query_one("#page-content").query(Page):
            page.context = self._page_context()

    def action_refresh(self) -> None:
        """Reload the visible page from disk."""
        page = self._page_for(self._current.key)
        if page is not None:
            page.refresh_data()
            self.notify(tr("Reloaded."), timeout=2)

    def _page_for(self, key: str) -> Page | None:
        matches = self.query(f"#page-{key}")
        return matches.first(Page) if matches else None

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
            self._workbench_keymap.help_text(),
            title=tr("Keyboard shortcuts"),
            timeout=15,
        )

    def action_language(self) -> None:
        """Pick the interface language from a list; it applies at once."""
        names = [name for _code, name in LANGUAGES]
        now = dict(LANGUAGES)[language()]

        def chosen(name: str | None) -> None:
            if name is not None:
                code = next(c for c, n in LANGUAGES if n == name)
                self.set_language(code)

        self.push_screen(
            ChoiceDialog(
                tr("Interface language"),
                names,
                current=now,
                note=tr("It applies at once and is remembered for the next runs."),
            ),
            chosen,
        )

    def set_language(self, code: str) -> None:
        """Switch the language now, keeping the open project and page."""
        try:
            code = set_language(code)
        except UnknownLanguageError as error:
            self.notify(str(error), severity="error")
            return
        try:
            store_language(AppConfig.load().config_dir, code)
            note = ""
        except (OSError, ConfigurationError):
            note = tr("It could not be remembered for the next runs.")
        self._retranslate()
        override = environ.get(ENVIRONMENT_VARIABLE)
        if override and normalize(override) != code:
            note = tr(
                "{variable} is set, so it wins on the next run.",
                variable=ENVIRONMENT_VARIABLE,
            )
        self.notify(f"{dict(LANGUAGES)[code]}. {note}".strip(), title=tr("Language"))

    def _retranslate(self) -> None:
        """Redraw the shell and the open page in the current language."""
        sidebar = self.query_one("#sidebar", OptionList)
        sidebar.clear_options()
        sidebar.add_options(self._sidebar_options())
        self.query_one("#header", AppHeader).set_project_label(
            _header_project_text(self._project)
        )
        self.query_one("#footer", AppFooter).set_status_line(
            _status_bar_text(self._project, self._workbench_keymap)
        )
        self.query_one("#context", Static).update(_context_text(self._project))
        self._show_page(self._current)
        sidebar.highlighted = sidebar.get_option_index(self._current.key)

    def action_focus_search(self) -> None:
        # Only the visible page counts: hidden pages stay mounted.
        scope = self._page_for(self._current.key) or self.screen
        fields = scope.query(".searchable")
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
        self.query_one("#page-title", Static).update(tr(item.title).upper())
        page = self._page_for(item.key)
        for other in self.query_one("#page-content").query(Page):
            other.display = other is page
        if page is not None:
            self.query_one("#page-body", Static).display = False
            page.refresh_data()
            # Update HelpBar with page-specific bindings
            help_bar = self.query_one("#help-bar", HelpBar)
            help_bar.set_page_bindings(list(page.BINDINGS))
            return
        self.query_one("#page-body", Static).display = True
        if item.key == "browser-preview":
            self.query_one("#page-body", Static).update(tr(BROWSER_HINT))
            panel = self.query_one("#browser-preview", BrowserPreview)
            panel.display = True
            panel.refresh_preview(force=True)
            # Browser preview has no specific bindings
            help_bar = self.query_one("#help-bar", HelpBar)
            help_bar.set_page_bindings([])
            return
        self.query_one("#page-body", Static).update(
            f"{format_status(Status.PENDING)}  {tr(UNAVAILABLE)}"
        )
        # No page bindings for unavailable modules
        help_bar = self.query_one("#help-bar", HelpBar)
        help_bar.set_page_bindings([])

    @staticmethod
    def _sidebar_options() -> list[Option]:
        options: list[Option] = []
        for index, section in enumerate(navigation.SECTIONS):
            # A blank line above each group keeps the groups apart.
            heading = tr(section.title).upper()
            options.append(
                Option(heading if index == 0 else f"\n{heading}", disabled=True)
            )
            options.extend(
                Option(tr(item.title).upper(), id=item.key) for item in section.items
            )
        return options
