"""AI Agent: talk to Alfred about the project (spec 4.18)."""

from dataclasses import replace

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from qa_workbench.ai import cli as ai_cli
from qa_workbench.ai.alfred import (
    LANGUAGES,
    AlfredSettings,
    AlfredSettingsError,
    ask_alfred,
    format_answer,
    list_models,
    load_settings,
    save_settings,
)
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.selection import REMOTE
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.components.agent_chat import AgentChat
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register

NO_PROJECT = "No project is open. Open Projects in the menu first."
TOOLS = "Tools (read only): ✓ get_record   ✓ list_records"
REMINDER = "Alfred analyses; it is not evidence. Facts need a record it really saw."


ENGINE_LABELS = {
    "auto": "auto - local engines first",
    "own": "own - Ollama on this machine",
    "opencode": "opencode - OpenCode server",
    "nvidia": "nvidia - hosted, data leaves this machine",
    "claude": "claude - Claude Code with your login, data leaves this machine",
}
STYLE_LABELS = {
    "balanced": "balanced",
    "concise": "concise - at most five short statements",
    "detailed": "detailed - explain the reasoning",
}
MENU_ITEMS = ("Engine", "Model", "Style", "Answer language", "Server addresses")


def server_fields(current: AlfredSettings) -> tuple[FormField, ...]:
    """The only settings that are typed: where each engine is."""
    return (
        FormField(
            "ollama_url", "Ollama URL", required=True, default=current.ollama_url
        ),
        FormField(
            "opencode_url", "OpenCode URL", required=True, default=current.opencode_url
        ),
        FormField(
            "nvidia_url", "NVIDIA URL", required=True, default=current.nvidia_url
        ),
    )


@register("ai-agent")
class AlfredPage(Page):
    BINDINGS = [
        Binding("ctrl+o", "configure", "Settings"),
        Binding("ctrl+g", "pick_model", "Models"),
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
            f"   Style: {s.style}   Ctrl+O settings   Ctrl+G models   Ctrl+L clear"
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
        current = self._current_or_default()
        language = next(
            (label for label, value in LANGUAGES if value == current.language),
            current.language,
        )
        entries = [
            f"Engine: {current.engine}",
            f"Model: {current.model or '(none yet)'}",
            f"Style: {current.style}",
            f"Answer language: {language or LANGUAGES[0][0]}",
            "Server addresses...",
        ]

        def chosen(entry: str | None) -> None:
            if entry is None:
                return
            index = entries.index(entry)
            if index == 0:
                self._pick_setting(
                    "Engine", "engine", [(v, k) for k, v in ENGINE_LABELS.items()]
                )
            elif index == 1:
                self.action_pick_model()
            elif index == 2:
                self._pick_setting(
                    "Style", "style", [(v, k) for k, v in STYLE_LABELS.items()]
                )
            elif index == 3:
                self._pick_setting("Answer language", "language", list(LANGUAGES))
            else:
                self._edit_servers()

        self.app.push_screen(
            ChoiceDialog(
                "Alfred settings",
                entries,
                note="Choose what to change. Nothing here needs typing.",
            ),
            chosen,
        )

    def _current_or_default(self) -> AlfredSettings:
        try:
            return self._settings()
        except AlfredSettingsError:
            return AlfredSettings()  # a broken file is replaced by what is saved

    def _pick_setting(
        self, title: str, field: str, options: list[tuple[str, str]]
    ) -> None:
        """Pick one value from a list; (label, value) pairs. Back to the menu after."""
        current = self._current_or_default()
        labels = [label for label, _ in options]
        now = next((lb for lb, v in options if v == getattr(current, field)), "")

        def chosen(label: str | None) -> None:
            if label is not None:
                value = dict(options)[label]
                try:
                    save_settings(
                        self.context.repository().root,
                        replace(current, **{field: value}),
                    )
                except (AlfredSettingsError, OSError) as error:
                    self.app.notify(str(error), severity="error")
                else:
                    self.refresh_data()
                    self.app.notify(f"{title} set to {label.split(' - ')[0]}.")
            self.action_configure()

        self.app.push_screen(ChoiceDialog(title, labels, current=now), chosen)

    def _edit_servers(self) -> None:
        root = self.context.repository().root
        current = self._current_or_default()

        def commit(values: dict[str, str]) -> str | None:
            try:
                save_settings(root, replace(current, **values))
            except (AlfredSettingsError, OSError) as error:
                return str(error)
            return None

        def done(values: dict[str, str] | None) -> None:
            if values is not None:
                self.refresh_data()
                self.app.notify("The server addresses were saved.")
            self.action_configure()

        self.app.push_screen(
            FormDialog(
                "Server addresses",
                server_fields(current),
                submit_label="Save",
                commit=commit,
            ),
            done,
        )

    def action_pick_model(self) -> None:
        project = self.context.project
        if project is None:
            self.app.notify(NO_PROJECT, severity="warning")
            return
        if project.archived:
            self.app.notify(f"{project.id} is archived and cannot be changed.")
            return
        try:
            settings = self._settings()
            repository = self.context.repository()
        except AlfredSettingsError as error:
            self.app.notify(f"Settings are unreadable: {error}", severity="error")
            return
        http = ai_cli.default_http()
        self.app.notify("Asking the engine for its models...")

        def work() -> None:
            try:
                engine, models = list_models(settings, repository, http)
            except (ProviderError, StorageError, OSError) as error:
                self.app.call_from_thread(self._models_failed, str(error))
            else:
                self.app.call_from_thread(self._choose_model, settings, engine, models)

        self.run_worker(work, thread=True, exclusive=True, name="alfred-models")

    def _models_failed(self, message: str) -> None:
        self.app.notify(f"Could not list the models: {message}", severity="error")

    def _choose_model(
        self, settings: AlfredSettings, engine: str, models: list[str]
    ) -> None:
        if not models:
            self.app.notify(f"The {engine} engine lists no models.", severity="warning")
            return
        note = (
            "Remote engine: questions and project context are sent off this machine."
            if engine in REMOTE
            else ""
        )

        def chosen(model: str | None) -> None:
            if model is None:
                return
            try:
                save_settings(
                    self.context.repository().root, replace(settings, model=model)
                )
            except (AlfredSettingsError, OSError) as error:
                self.app.notify(str(error), severity="error")
                return
            self.refresh_data()
            self.app.notify(f"Model set to {model}.")

        self.app.push_screen(
            ChoiceDialog(
                f"Models of {engine}", models, current=settings.model, note=note
            ),
            chosen,
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
        runner = ai_cli.default_runner()

        def work() -> None:
            try:
                reply = ask_alfred(settings, repository, http, event.text, runner)
            except ValueError as error:
                self.app.call_from_thread(self._finish, "notice", str(error))
            except NoProviderAvailable as error:
                self.app.call_from_thread(self._finish, "notice", str(error))
            except (ProviderError, StorageError, OSError) as error:
                hint = (
                    " Press Ctrl+G to choose one."
                    if "no model is configured" in str(error)
                    else ""
                )
                self.app.call_from_thread(
                    self._finish, "notice", f"Failed: {error}{hint}"
                )
            else:
                lines = format_answer(reply)
                if reply.attached:
                    lines.append(f"(attached: {', '.join(reply.attached)})")
                if reply.not_found:
                    lines.append(
                        f"(not found, so not attached: {', '.join(reply.not_found)})"
                    )
                remote = " - remote: data left this machine" if reply.remote else ""
                lines.append(f"(engine: {reply.engine}{remote})")
                self.app.call_from_thread(self._finish, "answer", "\n".join(lines))

        self.run_worker(work, thread=True, exclusive=True, name="alfred")

    def _finish(self, kind: str, text: str) -> None:
        chat = self.query_one(AgentChat)
        (chat.add_assistant if kind == "answer" else chat.add_notice)(text)
        chat.set_busy(False)
