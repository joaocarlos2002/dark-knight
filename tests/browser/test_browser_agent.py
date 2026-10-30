from pathlib import Path

import pytest
from fake_browser import FakeDriver

from qa_workbench.browser.agent import BrowserAgent, register_artifacts
from qa_workbench.browser.errors import AssertionFailed, BrowserError
from qa_workbench.browser.ports import BrowserMode, redact_url
from qa_workbench.browser.preview import PreviewChannel, PreviewController
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository


def _agent(tmp_path: Path, driver: FakeDriver, **options: object) -> BrowserAgent:
    return BrowserAgent(driver=driver, artifacts_dir=tmp_path / "run", **options)  # type: ignore[arg-type]


def test_actions_are_recorded_and_observations_kept(tmp_path: Path) -> None:
    driver = FakeDriver(texts={"h1": "Welcome back"}, visible={"#login"})
    agent = _agent(tmp_path, driver)

    with agent:
        agent.navigate("https://app.test/login")
        agent.fill("#user", "ada")
        agent.click("#login")
        agent.expect_text("h1", "Welcome")
        agent.expect_visible("#login")

    assert [a.label for a in agent.actions][:2] == [
        "navigate https://app.test/login",
        "fill #user",
    ]
    assert all(a.ok for a in agent.actions)
    assert len(agent.observations.console_errors) == 1
    assert agent.observations.http_failures[0].status == 500
    assert driver.sessions[0].closed


def test_filled_values_never_reach_the_action_log(tmp_path: Path) -> None:
    agent = _agent(tmp_path, FakeDriver())
    with agent:
        agent.fill("#password", "hunter2-secret")

    assert "hunter2" not in " ".join(a.label for a in agent.actions)


def test_failed_check_is_a_finding_not_a_browser_error(tmp_path: Path) -> None:
    agent = _agent(tmp_path, FakeDriver(texts={"h1": "Error 404"}))
    with agent:
        with pytest.raises(AssertionFailed) as raised:
            agent.expect_text("h1", "Welcome")
        assert not isinstance(raised.value, BrowserError)
        assert raised.value.actual == "Error 404"
        with pytest.raises(AssertionFailed):
            agent.expect_visible("#missing")


def test_browser_fault_keeps_context_and_is_recorded(tmp_path: Path) -> None:
    agent = _agent(tmp_path, FakeDriver(broken_selectors={"#gone"}))
    with agent:
        with pytest.raises(BrowserError, match="#gone"):
            agent.click("#gone")

    failed = [a for a in agent.actions if not a.ok]
    assert failed and "element not found" in failed[0].error


def test_actions_before_start_are_refused(tmp_path: Path) -> None:
    agent = _agent(tmp_path, FakeDriver())

    with pytest.raises(BrowserError, match="not started"):
        agent.navigate("https://app.test")


def test_launch_failure_propagates_and_releases_the_run(tmp_path: Path) -> None:
    driver = FakeDriver()
    driver.launch_error = BrowserError("no chromium")
    agent = _agent(tmp_path, driver)

    with pytest.raises(BrowserError, match="no chromium"):
        agent.start()
    driver.launch_error = None
    agent.start()  # a failed start does not block a retry
    agent.close()


def test_screenshot_failure_is_separate_from_the_test_result(tmp_path: Path) -> None:
    agent = _agent(tmp_path, FakeDriver(fail_screenshots=True))
    with agent:
        agent.navigate("https://app.test")
        assert agent.screenshot("home") is None

    assert agent.screenshot_failures
    assert all(a.ok for a in agent.actions)


def test_screenshots_trace_become_evidence(tmp_path: Path) -> None:
    agent = _agent(tmp_path, FakeDriver())
    with agent:
        agent.navigate("https://app.test")
        agent.screenshot("home page")
    artifacts = agent.close()
    repository = MarkdownRepository(tmp_path / "project", [EVIDENCE_SCHEMA])

    records = register_artifacts(EvidenceStore(repository), artifacts)

    assert len(records) == 2  # the screenshot and the trace
    assert {r.metadata["source"] for r in records} == {"playwright"}


def test_visible_mode_launches_a_headed_browser(tmp_path: Path) -> None:
    driver = FakeDriver()
    agent = _agent(tmp_path, driver, controller=PreviewController(BrowserMode.VISIBLE))
    with agent:
        pass

    assert driver.sessions[0].options.headless is False


def test_preview_publishes_frames_at_the_configured_rate(tmp_path: Path) -> None:
    channel = PreviewChannel(tmp_path / "preview")
    driver = FakeDriver()
    agent = _agent(
        tmp_path, driver, channel=channel, refresh_seconds=5, clock=lambda: 0.0
    )
    with agent:
        agent.navigate("https://app.test")
        agent.click("a")
        agent.click("b")

    # the clock never advances, so only the first action is inside a new window
    assert driver.sessions[0].screenshots_taken == 1
    state = channel.read()
    assert state is not None and state.execution_state == "finished"
    assert state.mode == "preview"
    assert channel.latest_frame() is not None


def test_headless_mode_does_not_capture_frames(tmp_path: Path) -> None:
    driver = FakeDriver()
    agent = _agent(
        tmp_path,
        driver,
        channel=PreviewChannel(tmp_path / "preview"),
        controller=PreviewController(BrowserMode.HEADLESS),
    )
    with agent:
        agent.navigate("https://app.test")

    assert driver.sessions[0].screenshots_taken == 0


def test_urls_hide_credentials_in_the_query_string() -> None:
    assert redact_url("https://a.test/x?token=abc&page=2") == (
        "https://a.test/x?token=[redacted]&page=2"
    )
    assert redact_url("https://a.test/x") == "https://a.test/x"
