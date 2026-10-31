from pathlib import Path

import pytest
from fake_ai import FakeHttp, ok

from qa_workbench.ai.errors import ProviderRateLimited, ProviderUnavailable
from qa_workbench.ai.guarded import GuardedJsonHttp
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard
from qa_workbench.security.settings import SecuritySettings

REMOTE = "https://nim.example.test/v1/models"


def _guarded(tmp_path: Path, **settings) -> tuple[GuardedJsonHttp, FakeHttp, AuditLog]:
    inner = FakeHttp({("GET", "/models"): ok({"data": []})})
    audit = AuditLog(tmp_path)
    guard = ActionGuard(SecuritySettings(**settings), audit)
    return GuardedJsonHttp(inner, guard), inner, audit


def test_a_host_that_is_not_allowed_gets_nothing_and_the_hint_says_how(
    tmp_path: Path,
) -> None:
    http, inner, _ = _guarded(tmp_path)

    with pytest.raises(ProviderUnavailable, match="nothing was sent") as error:
        http.request("GET", REMOTE, headers={"Authorization": "Bearer secret-key"})

    assert inner.calls == []
    assert "--allow-host nim.example.test" in str(error.value)
    assert "secret-key" not in str(error.value)


def test_an_allowed_host_is_audited_without_the_body_or_headers(
    tmp_path: Path,
) -> None:
    http, inner, audit = _guarded(tmp_path, allowed_hosts=("nim.example.test",))

    http.request(
        "GET", REMOTE, body={"q": "private"}, headers={"Authorization": "Bearer k1"}
    )

    assert len(inner.calls) == 1
    entries = [e for e in audit.entries() if e.kind == "action_allowed"]
    assert entries and entries[0].data["detail"] == f"GET {REMOTE}"
    assert "private" not in str(entries) and "k1" not in str(entries)


def test_a_local_server_is_in_scope_and_still_audited(tmp_path: Path) -> None:
    http, inner, audit = _guarded(tmp_path)

    http.request("GET", "http://127.0.0.1:11434/models")

    assert len(inner.calls) == 1
    assert [e.kind for e in audit.entries()] == ["action_allowed"]


def test_the_rate_limit_applies_to_engine_requests(tmp_path: Path) -> None:
    http, inner, _ = _guarded(
        tmp_path, allowed_hosts=("nim.example.test",), max_requests_per_minute=1
    )
    http.request("GET", REMOTE)

    with pytest.raises(ProviderRateLimited, match="Rate limit"):
        http.request("GET", REMOTE)
    assert len(inner.calls) == 1
