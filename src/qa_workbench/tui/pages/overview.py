"""Overview: the state of the project's quality, from its records (spec 4.1)."""

import getpass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Static

from qa_workbench.ai import cli as ai_cli
from qa_workbench.ai.alfred import (
    AlfredSettings,
    AlfredSettingsError,
    choose_provider,
)
from qa_workbench.ai.alfred import load_settings as load_alfred_settings
from qa_workbench.ai.errors import NoProviderAvailable, ProviderError
from qa_workbench.ai.populate import pending_requirements, populate
from qa_workbench.ai.selection import REMOTE
from qa_workbench.storage.errors import StorageError
from qa_workbench.tui.browse_review import pending_count
from qa_workbench.tui.components.dialog import ConfirmationDialog
from qa_workbench.tui.components.metric import MetricPanel
from qa_workbench.tui.components.states import EmptyState
from qa_workbench.tui.components.table import DataTable
from qa_workbench.tui.data import OverviewData, build_overview
from qa_workbench.tui.pages.base import Page
from qa_workbench.tui.pages.registry import register
from qa_workbench.tui.status import Status, format_status

NO_PROJECT = "No project is open."
NO_PROJECT_HINT = "Open Projects in the menu to create or select one."


def identity_text(data: OverviewData) -> str:
    project = data.project
    environments = ", ".join(f"{e.name} ({e.url})" for e in project.environments)
    return "\n".join(
        [
            f"Project      {project.name}  [{project.id}]",
            f"Repository   {project.repository or '-'}",
            f"Environments {environments or '-'}",
        ]
    )


POPULATE_LIMIT = 5


@register("overview")
class OverviewPage(Page):
    BINDINGS = [Binding("p", "populate", "AI drafts")]

    def action_populate(self) -> None:
        """Ask the AI for draft test cases for requirements that have none."""
        project = self.context.project
        if project is None or project.archived:
            self.app.notify("Open a project that can be changed first.")
            return
        repository = self.context.repository()
        try:
            settings = load_alfred_settings(repository.root)
        except AlfredSettingsError:
            settings = AlfredSettings()
        targets = pending_requirements(repository, POPULATE_LIMIT)
        if not targets:
            self.app.notify("Every requirement already has a test case.")
            return
        remote = settings.engine in REMOTE
        ids = ", ".join(r.id for r in targets)
        message = (
            f"The AI ({settings.engine}) will read {len(targets)} requirement(s): "
            f"{ids}, and write draft test cases for them.\n\n"
            "They arrive in Review as drafts. Nothing is final, and nothing is "
            "published."
        )
        if remote:
            message += (
                "\n\nThis engine is remote: the requirement text leaves this machine."
            )

        def confirmed(go: bool | None) -> None:
            if go:
                self._populate(settings)

        self.app.push_screen(
            ConfirmationDialog("AI drafts", message, confirm_label="Start"), confirmed
        )

    def _populate(self, settings: AlfredSettings) -> None:
        repository = self.context.repository()
        http = ai_cli.default_http()
        runner = ai_cli.default_runner()
        self.app.notify("Asking the AI for drafts...", title="AI drafts")

        def work() -> None:
            try:
                choice = choose_provider(settings, repository, http, runner)
                report = populate(
                    repository,
                    choice.provider,
                    model=settings.model,
                    limit=POPULATE_LIMIT,
                    actor=getpass.getuser(),
                    language=settings.language,
                )
            except (NoProviderAvailable, ProviderError, StorageError, OSError) as error:
                self.app.call_from_thread(self._populated, str(error), True)
                return
            text = (
                f"{len(report.created)} draft case(s) created, "
                f"{len(report.failed)} requirement(s) not used. Review them in Review."
            )
            self.app.call_from_thread(self._populated, text, bool(report.failed))

        self.run_worker(work, thread=True, exclusive=True, name="ai-populate")

    def _populated(self, text: str, bad: bool) -> None:
        self.refresh_data()
        self.app.notify(
            text,
            title="AI drafts",
            severity="warning" if bad else "information",
            timeout=12,
        )

    def compose(self) -> ComposeResult:
        yield Static("", id="overview-identity", markup=False)
        yield Static("", id="overview-review", markup=False)
        with Horizontal(id="overview-metrics"):
            yield MetricPanel("Test cases", None, id="metric-cases")
            yield MetricPanel("Passed", None, id="metric-passed")
            yield MetricPanel("Failed", None, id="metric-failed")
            yield MetricPanel("Blocked", None, id="metric-blocked")
            yield MetricPanel("In progress", None, id="metric-progress")
        yield Static("RECENT EXECUTIONS", classes="section-title")
        yield DataTable(
            ["ID", "Result", "Time", "Case"],
            empty_message="No executions yet.",
            empty_hint="Create one with `batman executions create`.",
            id="overview-recent",
        )
        yield Static("PIPELINES", classes="section-title")
        yield EmptyState(
            "No pipelines are recorded in this project.",
            "Inspect GitLab with `batman gitlab pipelines`.",
        )
        yield Static("", id="overview-problems", markup=False)
        yield EmptyState(NO_PROJECT, NO_PROJECT_HINT, id="overview-empty")

    def refresh_data(self) -> None:
        project = self.context.project
        has_project = project is not None
        self.query_one("#overview-empty").display = not has_project
        selectors = ("#overview-identity", "#overview-review", "#overview-metrics")
        for selector in (*selectors, "#overview-recent"):
            self.query_one(selector).display = has_project
        if not has_project:
            return
        try:
            data = build_overview(self.context.repository(), project)
        except (StorageError, OSError, ValueError) as error:
            self.query_one("#overview-problems", Static).update(
                f"{format_status(Status.FAILED)}  The project's records could not "
                f"be read\n{error}\nNext step: check the project folder, then "
                "press Ctrl+R."
            )
            return
        self._show(data)

    def _show(self, data: OverviewData) -> None:
        self.query_one("#overview-identity", Static).update(identity_text(data))
        waiting = pending_count(self.context.repository())
        notes = []
        if waiting:
            notes.append(
                f"{waiting} AI record(s) waiting for your review (see Review)."
            )
        uncovered = len(pending_requirements(self.context.repository(), 50))
        if uncovered:
            notes.append(
                f"{uncovered} requirement(s) have no test case. Press P to let the AI "
                "draft them."
            )
        self.query_one("#overview-review", Static).update("\n".join(notes))
        self.query_one("#metric-cases", MetricPanel).set_value(data.test_cases)
        for key in ("passed", "failed", "blocked"):
            self.query_one(f"#metric-{key}", MetricPanel).set_value(data.results[key])
        self.query_one("#metric-progress", MetricPanel).set_value(data.in_progress)
        self.query_one("#overview-recent", DataTable).set_rows(
            [
                (
                    row.id,
                    (
                        row.id,
                        format_status(row.status) if row.status else row.status_text,
                        row.duration,
                        row.case,
                    ),
                )
                for row in data.recent
            ]
        )
        problems = self.query_one("#overview-problems", Static)
        if data.problems:
            shown = "\n".join(f"  - {p}" for p in data.problems[:5])
            count = len(data.problems)
            problems.update(f"{count} damaged record(s) are not counted:\n{shown}")
        else:
            problems.update("")
