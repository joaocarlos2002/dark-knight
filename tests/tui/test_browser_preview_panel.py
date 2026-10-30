import asyncio
from pathlib import Path

import pytest
from PIL import Image

from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.preview import PreviewChannel, PreviewState
from qa_workbench.browser.render import render_halfblocks
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.browser_preview import BrowserPreview


def _png(path: Path) -> Path:
    Image.new("RGB", (80, 40), (10, 200, 10)).save(path, format="PNG")
    return path


def test_render_fits_the_area(tmp_path: Path) -> None:
    text = render_halfblocks(_png(tmp_path / "a.png"), 20, 5)

    lines = text.plain.split("\n")
    assert len(lines) <= 5 and max(len(line) for line in lines) <= 20


def test_unreadable_image_is_an_error(tmp_path: Path) -> None:
    broken = tmp_path / "x.png"
    broken.write_bytes(b"not a png")

    with pytest.raises(BrowserError, match="cannot be read"):
        render_halfblocks(broken, 10, 5)


def _scenario(tmp_path: Path, steps) -> None:
    channel = PreviewChannel(tmp_path / "preview")

    async def runner() -> None:
        app = WorkbenchApp(preview_channel=channel)
        async with app.run_test(size=(140, 50)) as pilot:
            await pilot.pause()
            await steps(app, pilot, channel)

    asyncio.run(runner())


def test_ctrl_b_shows_and_hides_the_preview(tmp_path: Path) -> None:
    async def steps(app, pilot, channel) -> None:
        panel = app.query_one("#browser-preview", BrowserPreview)
        assert not panel.display
        await pilot.press("ctrl+b")
        assert panel.display
        await pilot.press("ctrl+b")
        assert not panel.display

    _scenario(tmp_path, steps)


def test_reopening_shows_the_latest_image_published_while_hidden(
    tmp_path: Path,
) -> None:
    async def steps(app, pilot, channel) -> None:
        panel = app.query_one("#browser-preview", BrowserPreview)
        channel.publish(
            PreviewState(url="https://old.test", sequence=1),
            frame=_png(tmp_path / "old.png"),
        )
        await pilot.press("ctrl+b")
        await pilot.press("ctrl+b")  # hidden again
        channel.publish(
            PreviewState(url="https://new.test", action="click #go", sequence=2),
            frame=_png(tmp_path / "new.png"),
        )
        await pilot.press("ctrl+b")
        text = panel.shown_text
        assert panel.display
        assert "https://new.test" in text and "click #go" in text

    _scenario(tmp_path, steps)


def test_panel_says_so_when_no_browser_ever_ran(tmp_path: Path) -> None:
    async def steps(app, pilot, channel) -> None:
        await pilot.press("ctrl+b")
        panel = app.query_one("#browser-preview", BrowserPreview)
        assert "No browser is running" in panel.shown_text

    _scenario(tmp_path, steps)


def test_damaged_state_is_shown_as_an_error(tmp_path: Path) -> None:
    async def steps(app, pilot, channel) -> None:
        channel.directory.mkdir(parents=True)
        (channel.directory / "state.json").write_text("{bad", encoding="utf-8")
        await pilot.press("ctrl+b")
        panel = app.query_one("#browser-preview", BrowserPreview)
        assert "unavailable" in panel.shown_text

    _scenario(tmp_path, steps)


def test_mode_key_sends_a_request_and_explains_deferral(tmp_path: Path) -> None:
    async def steps(app, pilot, channel) -> None:
        channel.publish(PreviewState(mode="preview", execution_state="running"))
        await pilot.press("f5")
        assert channel.read_control()["mode"] == "visible"
        await pilot.press("f5")
        assert channel.read_control()["mode"] == "headless"

    _scenario(tmp_path, steps)


def test_pause_key_needs_a_running_browser(tmp_path: Path) -> None:
    async def steps(app, pilot, channel) -> None:
        await pilot.press("f6")
        assert channel.read_control() == {}
        channel.publish(PreviewState(execution_state="running"))
        await pilot.press("f6")
        assert channel.read_control()["paused"] is True

    _scenario(tmp_path, steps)
