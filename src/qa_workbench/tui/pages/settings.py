"""Settings page: view and edit application configuration."""

from dataclasses import dataclass
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, RadioButton, RadioSet, Static

from qa_workbench.core.config import AppConfig
from qa_workbench.security.credentials import (
    SERVICES,
    CredentialError,
    default_store,
    token_report,
)
from qa_workbench.security.policy import AutonomyMode
from qa_workbench.security.settings import (
    SecuritySettings,
    load_settings,
    save_settings,
)
from qa_workbench.tui.components.form import FormDialog, FormField
from qa_workbench.tui.components.states import EmptyState
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register

NO_PROJECT = "No project is open. Open Projects in the menu first."


@dataclass(frozen=True)
class SettingsCategory:
    """A category of settings."""

    key: str
    title: str
    description: str


SETTINGS_CATEGORIES: tuple[SettingsCategory, ...] = (
    SettingsCategory(
        "general", "General", "Default project, environment, and provider"
    ),
    SettingsCategory("shortcuts", "Shortcuts", "Keyboard shortcut overrides"),
    SettingsCategory("security", "Security", "Project autonomy mode and allowed hosts"),
    SettingsCategory("browser", "Browser", "Default browser mode and capture settings"),
    SettingsCategory(
        "credentials", "API tokens", "Tokens kept by the application, never shown"
    ),
)


@register("settings")
class SettingsPage(Page):
    """View and edit application and project settings."""

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+r", "reset", "Reset to defaults"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._active_category = "general"
        self._config = AppConfig.load()
        self._security_settings: SecuritySettings | None = None
        self._dirty = False

    def compose(self) -> ComposeResult:
        yield Static("", id="settings-title", markup=False)
        yield Static("", id="settings-problems", markup=False)
        yield EmptyState(
            NO_PROJECT, "Open a project to view and edit settings.", id="settings-empty"
        )

        with Horizontal(id="settings-body"):
            # Category sidebar
            with RadioSet(id="settings-categories"):
                for cat in SETTINGS_CATEGORIES:
                    yield RadioButton(cat.title, id=f"cat-{cat.key}", name="category")

            # Settings form area
            with Vertical(id="settings-form-area"):
                yield Static("", id="settings-form-title", classes="section-title")
                yield Static("", id="settings-form", markup=False)
                with Horizontal(id="settings-actions"):
                    yield Button("Save Changes", id="save-btn", variant="primary")
                    yield Button("Reset", id="reset-btn")

    def on_mount(self) -> None:
        # Select the first category by default
        radio = self.query_one("#cat-general", RadioButton)
        radio.value = True
        self._show_category("general")

    def refresh_data(self) -> None:
        project = self.context.project
        has_project = project is not None
        self.query_one("#settings-empty").display = not has_project
        self.query_one("#settings-body").display = has_project
        if has_project:
            self._config = AppConfig.load()
            try:
                self._security_settings = load_settings(self.context.repository().root)
            except Exception:
                self._security_settings = SecuritySettings()
            self._show_category(self._active_category)

    def _show_category(self, category: str) -> None:
        self._active_category = category
        form = self.query_one("#settings-form", Static)
        title = self.query_one("#settings-form-title", Static)

        cat = next(c for c in SETTINGS_CATEGORIES if c.key == category)
        title.update(cat.title)

        if category == "general":
            form.update(self._render_general())
        elif category == "shortcuts":
            form.update(self._render_shortcuts())
        elif category == "security":
            form.update(self._render_security())
        elif category == "browser":
            form.update(self._render_browser())
        elif category == "credentials":
            form.update(self._render_credentials())

    def _render_general(self) -> str:
        """Render the general settings as a form."""
        lines = [
            f"Default project: {self._config.data_dir}",
            f"Log level: {self._config.log_level}",
            f"Log file: {self._config.log_file or '-'}",
            "",
            "These are global settings stored in config.toml.",
            "Use the CLI or edit the file directly to change them.",
        ]
        return "\n".join(lines)

    def _render_shortcuts(self) -> str:
        """Render the shortcuts settings."""
        lines = ["Current shortcut overrides (config.toml [shortcuts]):", ""]
        if self._config.shortcuts:
            for action, key in self._config.shortcuts.items():
                lines.append(f"  {action}: {key}")
        else:
            lines.append("  (none — using defaults)")
        lines += [
            "",
            "To change shortcuts, edit config.toml:",
            "  [shortcuts]",
            '  toggle_context = "f3"',
        ]
        return "\n".join(lines)

    def _render_security(self) -> str:
        """Render the security settings."""
        if self._security_settings is None:
            return "Security settings not loaded."

        s = self._security_settings
        lines = [
            f"Autonomy mode: {s.mode.value}",
            f"Authorized environments: {', '.join(s.authorized_environments) or '-'}",
            f"Allowed hosts: {', '.join(s.allowed_hosts) or '-'}",
            f"Max requests/minute: {s.max_requests_per_minute}",
            f"Timeout (seconds): {s.timeout_seconds}",
            f"Max retries: {s.max_retries}",
            f"Data policy: {s.data_policy}",
            "",
            "These are per-project settings stored in security/settings.yaml.",
            "Use the form dialog (Ctrl+S) to change them.",
        ]
        return "\n".join(lines)

    def _render_browser(self) -> str:
        """Render the browser settings."""
        lines = [
            "Default browser mode: preview",
            "Capture console: enabled",
            "Capture network: enabled",
            "Save traces: on failure",
            "",
            "These are global settings. Edit config.toml to change them.",
        ]
        return "\n".join(lines)

    def _render_credentials(self) -> str:
        """Which tokens are set and where from; a value is never shown."""
        try:
            report = token_report(default_store())
        except CredentialError as error:
            return str(error)
        lines = [
            f"{variable:<24} {f'set ({source})' if source else 'not set'}"
            for variable, source in report
        ]
        lines += [
            "",
            "Stored outside any project, in your configuration folder. An",
            "environment variable of the same name wins over the stored value.",
            "Save Changes sets a token; Reset removes a stored one.",
        ]
        return "\n".join(lines)

    def _credentials_form(self, *, remove: bool) -> None:
        """Set or remove a stored token. The value is typed hidden and is never
        shown, logged, or echoed back, not even in an error."""
        fields = [
            FormField(
                "service",
                f"Service ({', '.join(SERVICES)}) or variable name",
                required=True,
            )
        ]
        if not remove:
            fields.append(FormField("token", "Token", required=True, secret=True))

        def commit(values: dict[str, str]) -> str | None:
            store = default_store()
            if store is None:
                return (
                    "The configuration is invalid, so there is nowhere to keep tokens."
                )
            try:
                if remove:
                    done = store.remove(values["service"])
                    message = "Token removed." if done else "That token was not stored."
                else:
                    store.set(values["service"], values["token"])
                    message = "Token stored. The value is not shown again."
            except CredentialError as error:
                return str(error)
            self.app.notify(message, title="API tokens")
            return None

        self.app.push_screen(
            FormDialog(
                "Remove a token" if remove else "Set a token",
                fields,
                submit_label="Remove" if remove else "Save",
                commit=commit,
            ),
            lambda _: self._show_category("credentials"),
        )

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        event.stop()
        if event.radio_set.id == "settings-categories":
            cat_key = event.pressed.id.removeprefix("cat-")
            self._show_category(cat_key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "reset-btn":
            self.action_reset()

    def action_save(self) -> None:
        """Save the current category's settings."""
        if self._active_category == "credentials":
            self._credentials_form(remove=False)
        elif self._active_category == "security" and self._security_settings:
            # Show a form dialog to edit security settings
            self._show_security_form()
        else:
            self.app.notify(
                "Edit config.toml directly for this category.", severity="warning"
            )

    def action_reset(self) -> None:
        """Reset the current category to defaults."""
        if self._active_category == "credentials":
            self._credentials_form(remove=True)
            return
        self.app.notify("Use the CLI or edit config.toml to reset.", severity="warning")

    def _show_security_form(self) -> None:
        """Show a form to edit security settings."""
        if not self.context.project:
            self.app.notify(NO_PROJECT, severity="error")
            return

        s = self._security_settings
        fields = [
            FormField(
                "mode",
                "Autonomy mode",
                placeholder="assisted, semi_autonomous, controlled_autonomous",
                default=s.mode.value,
                required=True,
            ),
            FormField(
                "authorized_environments",
                "Authorized environments (comma-separated)",
                placeholder="staging, production",
                default=", ".join(s.authorized_environments),
            ),
            FormField(
                "allowed_hosts",
                "Allowed hosts (comma-separated, .suffix allowed)",
                placeholder=".example.com, api.example.com",
                default=", ".join(s.allowed_hosts),
            ),
            FormField(
                "max_requests_per_minute",
                "Max requests per minute",
                placeholder="60",
                default=str(s.max_requests_per_minute),
                required=True,
            ),
            FormField(
                "timeout_seconds",
                "Timeout (seconds)",
                placeholder="30",
                default=str(s.timeout_seconds),
                required=True,
            ),
            FormField(
                "max_retries",
                "Max retries",
                placeholder="0",
                default=str(s.max_retries),
                required=True,
            ),
            FormField(
                "data_policy",
                "Data policy",
                placeholder="sanitize-before-persist",
                default=s.data_policy,
                required=True,
            ),
        ]

        def validate(values: dict[str, str]) -> str | None:
            try:
                AutonomyMode(values["mode"])
            except ValueError:
                return (
                    "Invalid mode: must be one of "
                    f"{', '.join(m.value for m in AutonomyMode)}"
                )
            try:
                max_rpm = int(values["max_requests_per_minute"])
                if max_rpm < 1:
                    return "Max requests per minute must be at least 1"
            except ValueError:
                return "Max requests per minute must be an integer"
            try:
                timeout = float(values["timeout_seconds"])
                if timeout <= 0:
                    return "Timeout must be positive"
            except ValueError:
                return "Timeout must be a number"
            try:
                retries = int(values["max_retries"])
                if retries < 0:
                    return "Max retries cannot be negative"
            except ValueError:
                return "Max retries must be an integer"

            # Validate hosts
            hosts = [h.strip() for h in values["allowed_hosts"].split(",") if h.strip()]
            for host in hosts:
                bare = host.removeprefix(".")
                if not bare or "*" in host or "/" in host or ":" in host or " " in host:
                    return (
                        f"Invalid host '{host}': must be a host name or "
                        "'.suffix' without wildcards, paths, or ports"
                    )
            return None

        def commit(values: dict[str, str]) -> str | None:
            # Parse and create new settings
            try:
                new_settings = SecuritySettings(
                    mode=AutonomyMode(values["mode"]),
                    authorized_environments=tuple(
                        e.strip()
                        for e in values["authorized_environments"].split(",")
                        if e.strip()
                    ),
                    allowed_hosts=tuple(
                        h.strip()
                        for h in values["allowed_hosts"].split(",")
                        if h.strip()
                    ),
                    max_requests_per_minute=int(values["max_requests_per_minute"]),
                    timeout_seconds=float(values["timeout_seconds"]),
                    max_retries=int(values["max_retries"]),
                    data_policy=values["data_policy"],
                )
            except Exception as error:
                return str(error)

            # Save to disk
            try:
                save_settings(self.context.repository().root, new_settings)
                # Write audit log entry
                from qa_workbench.security.audit import AuditLog

                AuditLog(self.context.repository().root).append(
                    "security_settings_changed",
                    {
                        "changed_by": "TUI user",
                        "old_mode": s.mode.value,
                        "new_mode": new_settings.mode.value,
                    },
                )
            except Exception as error:
                return f"Failed to save: {error}"

            self._security_settings = new_settings
            self.refresh_data()
            self.app.notify("Security settings saved and audited.", timeout=3)
            return None

        self.app.push_screen(
            FormDialog(
                "Security Settings",
                fields,
                submit_label="Save",
                validate=validate,
                commit=commit,
            )
        )
