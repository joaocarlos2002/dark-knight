import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fake_browser import FakeDriver

from qa_workbench.browser.agent import BrowserAgent, is_local
from qa_workbench.browser.chromium import probe_chromium
from qa_workbench.browser.errors import BrowserError
from qa_workbench.browser.playwright_driver import PlaywrightDriver
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, Cancelled, RateLimitExceeded
from qa_workbench.security.settings import SecuritySettings


def _guard(tmp_path: Path, **settings) -> ActionGuard:
    options = {"allowed_hosts": ("staging.example.com",), **settings}
    return ActionGuard(SecuritySettings(**options), AuditLog(tmp_path / "audit"))


def _agent(tmp_path: Path, driver: FakeDriver, guard=None) -> BrowserAgent:
    return BrowserAgent(driver=driver, artifacts_dir=tmp_path / "run", guard=guard)


def test_without_a_project_scope_only_local_addresses_open(tmp_path: Path) -> None:
    driver = FakeDriver()
    agent = _agent(tmp_path, driver)
    with agent:
        agent.navigate("http://localhost:3000/")
        agent.navigate("http://127.0.0.1/x")
        with pytest.raises(BrowserError, match="Only local addresses"):
            agent.navigate("https://staging.example.com/")

    assert [c for c in driver.sessions[0].calls if c[0] == "navigate"] == [
        ("navigate", "http://localhost:3000/"),
        ("navigate", "http://127.0.0.1/x"),
    ]


def test_is_local() -> None:
    assert is_local("http://localhost:8080/a") and is_local("file:///tmp/a.html")
    assert is_local("https://127.0.0.1/") and is_local("http://[::1]:80/")
    assert not is_local("https://localhost.evil.test/")
    assert not is_local("https://example.com/")


def test_an_authorized_host_opens_and_is_audited(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    driver = FakeDriver()
    with _agent(tmp_path, driver, guard) as agent:
        agent.navigate("https://staging.example.com/login?token=abc123456")

    entry = guard.audit.entries()[0]
    assert entry.kind == "action_allowed" and entry.actor == "browser-agent"
    assert "abc123456" not in str(entry.data)  # query secrets never reach the log
    assert driver.sessions[0].calls[0][0] == "navigate"


def test_a_host_outside_the_project_scope_is_refused_before_any_request(
    tmp_path: Path,
) -> None:
    driver = FakeDriver()
    with _agent(tmp_path, driver, _guard(tmp_path)) as agent:
        with pytest.raises(BrowserError, match="not in the project's allowed hosts"):
            agent.navigate("https://prod.example.com/")

    assert driver.sessions[0].calls == []


def test_the_launch_filter_matches_the_project_scope(tmp_path: Path) -> None:
    driver = FakeDriver()
    with _agent(tmp_path, driver, _guard(tmp_path)):
        pass

    allow = driver.sessions[0].options.allow_request
    assert allow is not None
    assert allow("https://staging.example.com/app.js")
    assert allow("http://localhost:3000/")
    assert not allow("https://tracker.evil.test/pixel.gif")


def test_ending_on_an_unauthorized_url_stops_the_run(tmp_path: Path) -> None:
    driver = FakeDriver()
    agent = _agent(tmp_path, driver, _guard(tmp_path))
    with agent:
        session = driver.sessions[0]
        original = session.navigate

        def redirecting(url: str, *, timeout_ms: int) -> None:
            original(url, timeout_ms=timeout_ms)
            session.url = "https://elsewhere.evil.test/landing"

        session.navigate = redirecting  # type: ignore[method-assign]
        with pytest.raises(BrowserError, match="not authorized") as error:
            agent.navigate("https://staging.example.com/")

    assert "elsewhere.evil.test" in str(error.value)


def test_rate_limit_and_cancellation_stop_navigation(tmp_path: Path) -> None:
    limited = _guard(tmp_path / "a", max_requests_per_minute=1)
    with _agent(tmp_path, FakeDriver(), limited) as agent:
        agent.navigate("https://staging.example.com/1")
        with pytest.raises(RateLimitExceeded):
            agent.navigate("https://staging.example.com/2")

    cancelled = _guard(tmp_path / "b")
    cancelled.cancel("Ana", "wrong environment")
    with _agent(tmp_path, FakeDriver(), cancelled) as agent:
        with pytest.raises(Cancelled):
            agent.navigate("https://staging.example.com/")


# -- the real Chromium, against a local server (skipped when it is not installed) ----


class _Pages(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.2:{self.server.server_port}/landing"
            )
            self.end_headers()
            return
        body = (
            b"<html><head><title>Gotham</title></head><body><h1>Home</h1>"
            b'<img src="http://127.0.0.2:%d/pixel.gif"></body></html>'
            % self.server.server_port
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Pages)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


@pytest.mark.skipif(not probe_chromium().ready, reason="Chromium is not installed")
def test_real_chromium_blocks_unauthorized_subresources_and_redirects(
    tmp_path: Path, local_server
) -> None:
    port = local_server.server_port
    agent = BrowserAgent(
        driver=PlaywrightDriver(),
        artifacts_dir=tmp_path / "run",
        video=False,
        trace=False,
    )
    with agent:
        agent.navigate(f"http://127.0.0.1:{port}/")
        agent.expect_text("h1", "Home")
        with pytest.raises(BrowserError, match="ERR_NAME_NOT_RESOLVED"):
            agent.navigate(f"http://127.0.0.1:{port}/redirect")

    blocked = [
        e for e in agent.observations.network if e.failure and "blocked" in e.failure
    ]
    assert any("127.0.0.2" in e.url for e in blocked)
