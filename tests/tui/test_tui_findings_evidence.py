import asyncio
from pathlib import Path

from textual.widgets import Button, Input, OptionList, Static

from qa_workbench.browser.preview import PreviewChannel
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.components.file_dialog import FileDialog
from qa_workbench.tui.components.form import FormDialog
from qa_workbench.workspace import repository_for


async def _until(pilot, condition, tries: int = 80) -> None:
    for _ in range(tries):
        if condition():
            return
        await pilot.pause(0.05)
    raise AssertionError("the expected change never happened")


def _run(tmp_path: Path, page: str, scenario) -> None:
    project = ProjectRepository(tmp_path).create("Demo")
    repository = repository_for(tmp_path, project)

    async def runner() -> None:
        app = WorkbenchApp(
            project, preview_channel=PreviewChannel(tmp_path / "p"), data_dir=tmp_path
        )
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            app.navigate(page)
            await pilot.pause()
            await scenario(app, pilot, repository)

    asyncio.run(runner())


def _fill(app, **values: str) -> None:
    for key, value in values.items():
        app.screen.query_one(f"#field-{key}", Input).value = value


async def _submit(app, pilot) -> None:
    app.screen.query_one("#submit", Button).press()
    await pilot.pause()


async def _choose(app, pilot, label: str) -> None:
    await _until(pilot, lambda: isinstance(app.screen, ChoiceDialog))
    options = app.screen.query_one(OptionList)
    texts = [
        str(options.get_option_at_index(i).prompt) for i in range(options.option_count)
    ]
    options.highlighted = texts.index(label)
    await pilot.press("enter")


async def _record(app, pilot, title: str = "Pay button dead") -> None:
    await pilot.press("n")
    await _until(pilot, lambda: isinstance(app.screen, FormDialog))
    _fill(
        app,
        title=title,
        environment="staging 1.4.0",
        steps="Open the cart; Press Pay",
        expected="Payment page opens",
        observed="Nothing happens",
    )
    await _submit(app, pilot)


def test_a_finding_is_recorded_as_suspected_without_typing_a_classification(
    tmp_path,
) -> None:
    async def scenario(app, pilot, repository) -> None:
        await _record(app, pilot)
        await _until(pilot, lambda: repository.list_records("BUG").records)
        meta = repository.get("BUG-001").metadata
        assert meta["status"] == "suspected" and meta["steps"] == [
            "Open the cart",
            "Press Pay",
        ]

    _run(tmp_path, "bug-hunting", scenario)


def test_a_defect_cannot_be_confirmed_without_evidence_and_the_form_stays_open(
    tmp_path,
) -> None:
    async def scenario(app, pilot, repository) -> None:
        await _record(app, pilot)
        await _until(pilot, lambda: repository.list_records("BUG").records)

        await pilot.press("c")
        await _choose(app, pilot, "reproduced")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, by="Ana", why="It happened twice", attempts="3", reproductions="2")
        await _submit(app, pilot)

        assert isinstance(app.screen, FormDialog)
        error = str(app.screen.query_one("#form-error", Static).render())
        assert "evidence" in error
        assert app.screen.query_one("#field-why", Input).value == "It happened twice"
        assert repository.get("BUG-001").metadata["status"] == "suspected"

    _run(tmp_path, "bug-hunting", scenario)


def test_evidence_is_attached_from_the_file_chooser_and_then_the_defect_is_confirmed(
    tmp_path,
) -> None:
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"not really a png")

    async def scenario(app, pilot, repository) -> None:
        await _record(app, pilot)
        await _until(pilot, lambda: repository.list_records("BUG").records)

        await pilot.press("e")
        await _until(pilot, lambda: isinstance(app.screen, FileDialog))
        app.screen.choose(shot)
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, description="The button does nothing")
        await _submit(app, pilot)
        await _until(pilot, lambda: repository.get("BUG-001").metadata.get("evidence"))
        assert repository.get("BUG-001").metadata["evidence"] == ["EVD-001"]

        await pilot.press("c")
        await _choose(app, pilot, "reproduced")
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, by="Ana", why="Twice", attempts="3", reproductions="2")
        await _submit(app, pilot)
        await _until(
            pilot, lambda: repository.get("BUG-001").metadata["status"] == "reproduced"
        )
        history = repository.get("BUG-001").metadata["classification_history"]
        assert history[-1]["by"] == "Ana" and history[-1]["why"] == "Twice"

    _run(tmp_path, "bug-hunting", scenario)


def test_the_evidence_page_adds_a_file_and_verifies_integrity(tmp_path) -> None:
    log = tmp_path / "run.log"
    log.write_text("hello\n")

    async def scenario(app, pilot, repository) -> None:
        await pilot.press("a")
        await _until(pilot, lambda: isinstance(app.screen, FileDialog))
        app.screen.choose(log)
        await _until(pilot, lambda: isinstance(app.screen, FormDialog))
        _fill(app, description="The run log")
        await _submit(app, pilot)
        await _until(pilot, lambda: repository.list_records("EVD").records)
        assert len(repository.get("EVD-001").metadata["sha256"]) == 64

        await pilot.press("v")
        await _until(
            pilot, lambda: any("intact" in n.message for n in app._notifications)
        )

        store = EvidenceStore(repository)
        store.file_path(repository.get("EVD-001")).write_text("tampered\n")
        await pilot.press("v")
        await _until(
            pilot, lambda: any("not intact" in n.message for n in app._notifications)
        )

    _run(tmp_path, "evidence", scenario)


def test_the_file_dialog_can_be_cancelled(tmp_path) -> None:
    async def scenario(app, pilot, repository) -> None:
        await pilot.press("a")
        await _until(pilot, lambda: isinstance(app.screen, FileDialog))
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, FileDialog)
        assert not repository.list_records("EVD").records

    _run(tmp_path, "evidence", scenario)
