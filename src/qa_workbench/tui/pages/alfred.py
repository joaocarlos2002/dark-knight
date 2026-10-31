"""AI Agent: talk to Alfred about the project (spec 4.18)."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from qa_workbench.ai import cli as ai_cli
from qa_workbench.ai.alfred import (
    STYLES,
    AlfredSettings,
    AlfredSettingsError,
    ask_alfred,
    format_answer,
    load_settings,
    save_settings,
)
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.selection import MODES
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.components.agent_chat import AgentChat
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register

NO_PROJECT = "No project is open. Open Projects in the menu first."
TOOLS = "Tools (read only): ✓ get_record   ✓ list_records"
REMINDER = "Alfred analyses; it is not evidence. Facts need a record it really saw."


def settings_fields(current: AlfredSettings) -> tuple[FormField, ...]:
    return (
        FormField(
            "engine",
            f"Engine ({', '.join(MODES)})",
            required=True,
            default=current.engine,
        ),
        FormField(
            "model", "Model", "llama3.2   or   provider/model", default=current.model
        ),
        FormField(
            "style",
            f"Style ({', '.join(STYLES)})",
            required=True,
            default=current.style,
        ),
        FormField("language", "Answer language", "English", default=current.language),
        FormField(
            "ollama_url", "Ollama URL", required=True, default=current.ollama_url
        ),
        FormField(
            "opencode_url", "OpenCode URL", required=True, default=current.opencode_url
        ),
    )


@register("ai-agent")
class AlfredPage(Page):
    BINDINGS = [
        Binding("ctrl+o", "configure", "Settings"),
        Binding("ctrl+l", "clear_chat", "Clear"),
    ]

    def compose(self) -> ComposeResult:
        yield Static("", classes="page-hint", id="alfred-summary", markup=False)
        yield AgentChat(id="alfred-chat")
        yield Static(f"{TOOLS}\n{REMINDER}", classes="page-hint", id="alfred-footer")

    def focus_primary(self) -> None:
        self.query_one(AgentChat).focus_input()

    # -- settings ------------------------------------------------------------------

    def _settings(self) -> AlfredSettings:
        return load_settings(self.context.repository().root)

    def refresh_data(self) -> None:
        summary = self.query_one("#alfred-summary", Static)
        if self.context.project is None:
            summary.update(NO_PROJECT)
            return
        try:
            s = self._settings()
        except AlfredSettingsError as error:
            summary.update(f"Settings are unreadable: {error}")
            return
        context = f"{self.context.project.id} {self.context.project.name}"
        summary.update(
            f"Context: {context}   Engine: {s.engine}   Model: {s.model or '(default)'}"
            f"   Style: {s.style}   Ctrl+O settings   Ctrl+L clear"
        )

    def action_clear_chat(self) -> None:
        self.query_one(AgentChat).clear()

    def action_configure(self) -> None:
        project = self.context.project
        if project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return
        if project.archived:
            self.app.notify(f"{project.id} is archived and cannot be changed.")
            return
        root = self.context.repository().root
        try:
            current = load_settings(root)
        except AlfredSettingsError:
            current = AlfredSettings()  # a broken file is replaced by what is saved

        def commit(values: dict[str, str]) -> str | None:
            try:
                save_settings(root, AlfredSettings(**values))
            except (AlfredSettingsError, OSError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify("Alfred's settings were saved.")

        self.app.push_screen(
            FormDialog(
                "Alfred settings",
                settings_fields(current),
                submit_label="Save",
                commit=commit,
            ),
            done,
        )

    # -- asking ---------------------------------------------------------------------

    def on_agent_chat_submitted(self, event: AgentChat.Submitted) -> None:
        event.stop()
        chat = self.query_one(AgentChat)
        chat.add_user(event.text)
        if self.context.project is None:
            chat.add_notice(NO_PROJECT)
            return
        try:
            settings = self._settings()
            repository = self.context.repository()
        except AlfredSettingsError as error:
            chat.add_notice(f"Settings are unreadable: {error}")
            return
        chat.set_busy(True)
        # The model call can take a long time: it runs in a thread so the TUI
        # keeps responding. Looked up here so tests can replace the HTTP client.
        http = ai_cli.default_http()

        def work() -> None:
            try:
                reply = ask_alfred(settings, repository, http, event.text)
            except ValueError as error:
                self.app.call_from_thread(self._finish, "notice", str(error))
            except NoProviderAvailable as error:
                self.app.call_from_thread(self._finish, "notice", str(error))
            except (ProviderError, StorageError, OSError) as error:
                self.app.call_from_thread(self._finish, "notice", f"Failed: {error}")
            else:
                lines = format_answer(reply)
                if reply.attached:
                    lines.append(f"(attached: {', '.join(reply.attached)})")
                if reply.not_found:
                    lines.append(
                        f"(not found, so not attached: {', '.join(reply.not_found)})"
                    )
                lines.append(f"(engine: {reply.engine})")
                self.app.call_from_thread(self._finish, "answer", "\n".join(lines))

        self.run_worker(work, thread=True, exclusive=True, name="alfred")

    def _finish(self, kind: str, text: str) -> None:
        chat = self.query_one(AgentChat)
        (chat.add_assistant if kind == "answer" else chat.add_notice)(text)
        chat.set_busy(False)
