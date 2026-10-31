import json
from pathlib import Path

from fake_browser import FakeDriver

from qa_workbench.browser.agent import BrowserAgent, register_artifacts, write_logs
from qa_workbench.browser.ports import (
    ConsoleEntry,
    NetworkEntry,
    Observations,
)
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_a_run_leaves_a_console_log_and_a_network_log(tmp_path: Path) -> None:
    agent = BrowserAgent(driver=FakeDriver(), artifacts_dir=tmp_path / "run")
    with agent:
        agent.navigate("http://localhost/checkout")
    artifacts = agent.close()

    console = _read(artifacts.console_log)
    network = _read(artifacts.network_log)

    assert console["console"][0]["level"] == "error"
    assert console["console"][0]["text"] == "boom"
    assert network["requests"][0]["status"] == 500
    assert network["requests"][0]["failed"] is True and network["failed"] == 1
    kinds = [kind for _, kind in artifacts.files()]
    assert "console log" in kinds and "network log" in kinds


def test_secrets_in_console_text_and_urls_are_removed(tmp_path: Path) -> None:
    observations = Observations()
    observations.console.append(
        ConsoleEntry("error", "login failed, token=abc123secret99 password=hunter22")
    )
    observations.console.append(
        ConsoleEntry("warning", "ok", "http://l/?api_key=zzz999")
    )
    observations.page_errors.append("Unhandled: Bearer abcdefghijklmnop12345")
    observations.network.append(
        NetworkEntry("GET", "http://l/api?token=qqq888&page=2", 200, "xhr")
    )

    console_path, network_path = write_logs(tmp_path, observations)

    text = console_path.read_text(encoding="utf-8") + network_path.read_text(
        encoding="utf-8"
    )
    for secret in (
        "abc123secret99",
        "hunter22",
        "zzz999",
        "abcdefghijklmnop12345",
        "qqq888",
    ):
        assert secret not in text, secret
    assert "page=2" in text and "login failed" in text


def test_failed_requests_are_flagged_and_counted(tmp_path: Path) -> None:
    observations = Observations()
    observations.network += [
        NetworkEntry("GET", "http://l/ok", 200),
        NetworkEntry("GET", "http://l/missing", 404),
        NetworkEntry(
            "GET", "http://l/blocked", None, failure="blocked: host not authorized"
        ),
    ]

    _, network_path = write_logs(tmp_path, observations)

    data = _read(network_path)
    assert [r["failed"] for r in data["requests"]] == [False, True, True]
    assert data["failed"] == 2
    assert data["requests"][2]["failure"] == "blocked: host not authorized"


def test_an_empty_run_still_writes_valid_logs(tmp_path: Path) -> None:
    console_path, network_path = write_logs(tmp_path / "new" / "dir", Observations())

    assert _read(console_path) == {"console": [], "page_errors": []}
    assert _read(network_path) == {"requests": [], "failed": 0}


def test_the_logs_become_hashed_evidence(tmp_path: Path) -> None:
    agent = BrowserAgent(driver=FakeDriver(), artifacts_dir=tmp_path / "run")
    with agent:
        agent.navigate("http://localhost/")
    repository = MarkdownRepository(tmp_path / "project", [EVIDENCE_SCHEMA])
    store = EvidenceStore(repository)

    records = register_artifacts(store, agent.close())

    names = {r.metadata["original_name"] for r in records}
    assert {"console.json", "network.json", "trace.zip"} <= names
    assert all(store.verify(r.id) == [] for r in records)
    descriptions = {r.metadata["description"] for r in records}
    assert "console log captured by the Browser Agent" in descriptions
