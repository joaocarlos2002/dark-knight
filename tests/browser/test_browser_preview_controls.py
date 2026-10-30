import threading
import time
from pathlib import Path

import pytest
from fake_browser import FakeDriver

from qa_workbench.browser.agent import BrowserAgent
from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.ports import BrowserMode
from qa_workbench.browser.preview import PreviewChannel, PreviewController, PreviewState


def test_channel_round_trips_state_and_frame(tmp_path: Path) -> None:
    channel = PreviewChannel(tmp_path / "p")
    frame = tmp_path / "f.png"
    frame.write_bytes(b"png")

    assert channel.read() is None and channel.latest_frame() is None
    channel.publish(PreviewState(url="https://a.test", sequence=3), frame=frame)

    state = channel.read()
    assert state is not None and state.url == "https://a.test" and state.sequence == 3
    assert channel.latest_frame().read_bytes() == b"png"  # type: ignore[union-attr]


def test_damaged_state_is_an_error_not_an_idle_browser(tmp_path: Path) -> None:
    channel = PreviewChannel(tmp_path)
    (tmp_path / "state.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(BrowserError, match="unreadable"):
        channel.read()


def test_idle_mode_changes_apply_at_once() -> None:
    controller = PreviewController(BrowserMode.PREVIEW)

    change = controller.request_mode(BrowserMode.VISIBLE)

    assert change.applied and controller.mode is BrowserMode.VISIBLE


def test_running_switch_between_headless_and_preview_is_immediate() -> None:
    controller = PreviewController(BrowserMode.PREVIEW)
    controller.run_started()

    change = controller.request_mode(BrowserMode.HEADLESS)

    assert change.applied and controller.mode is BrowserMode.HEADLESS


def test_running_switch_to_visible_is_deferred_and_honest() -> None:
    controller = PreviewController(BrowserMode.PREVIEW)
    controller.run_started()

    change = controller.request_mode(BrowserMode.VISIBLE)

    assert not change.applied and "next run" in change.message
    assert controller.mode is BrowserMode.PREVIEW
    assert controller.pending_mode is BrowserMode.VISIBLE
    assert controller.run_finished() is BrowserMode.VISIBLE


def test_pause_blocks_until_resumed() -> None:
    controller = PreviewController()
    controller.pause()
    released = threading.Event()

    def waiter() -> None:
        controller.wait_if_paused()
        released.set()

    thread = threading.Thread(target=waiter)
    thread.start()
    time.sleep(0.05)
    assert not released.is_set()
    controller.resume()
    thread.join(timeout=2)
    assert released.is_set()


def test_hiding_the_preview_does_not_touch_the_run(tmp_path: Path) -> None:
    # The TUI only reads the channel; a run keeps publishing with nobody reading.
    channel = PreviewChannel(tmp_path / "p")
    agent = BrowserAgent(
        driver=FakeDriver(), artifacts_dir=tmp_path / "run", channel=channel
    )
    with agent:
        agent.navigate("https://app.test")
        first = channel.read()
        agent.click("#a")
        later = channel.read()

    assert first is not None and later is not None
    assert later.sequence > first.sequence
    assert all(a.ok for a in agent.actions)


def test_requests_from_another_process_reach_the_running_agent(tmp_path: Path) -> None:
    channel = PreviewChannel(tmp_path / "p")
    controller = PreviewController(BrowserMode.PREVIEW)
    driver = FakeDriver()
    agent = BrowserAgent(
        driver=driver,
        artifacts_dir=tmp_path / "run",
        channel=channel,
        controller=controller,
    )
    with agent:
        agent.navigate("https://app.test")
        channel.request(mode="visible")
        agent.click("#a")
        state = channel.read()
        assert state is not None and state.pending_mode == "visible"
        assert controller.mode is BrowserMode.PREVIEW  # restart needed: deferred

        channel.request(mode="headless")
        agent.click("#b")
        assert controller.mode is BrowserMode.HEADLESS


def test_pause_request_holds_the_next_action_until_resume(tmp_path: Path) -> None:
    channel = PreviewChannel(tmp_path / "p")
    agent = BrowserAgent(
        driver=FakeDriver(), artifacts_dir=tmp_path / "run", channel=channel
    )
    done = threading.Event()

    def run() -> None:
        with agent:
            agent.navigate("https://app.test")
            channel.request(paused=True)
            agent.click("#a")  # waits here
            done.set()

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.time() + 5
    while time.time() < deadline:
        state = channel.read()
        if state is not None and state.paused:
            break
        time.sleep(0.02)
    assert not done.is_set()
    channel.request(paused=False)
    thread.join(timeout=5)
    assert done.is_set()


def test_unknown_mode_in_control_file_is_ignored(tmp_path: Path) -> None:
    channel = PreviewChannel(tmp_path / "p")
    channel.request(mode="sideways")
    agent = BrowserAgent(
        driver=FakeDriver(), artifacts_dir=tmp_path / "run", channel=channel
    )
    with agent:
        agent.navigate("https://app.test")

    assert agent.controller.mode is BrowserMode.PREVIEW
