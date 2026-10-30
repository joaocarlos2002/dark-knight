from pathlib import Path

import pytest

from qa_workbench.security.policy import (
    SENSITIVE,
    AutonomyMode,
    Category,
    requires_approval,
)
from qa_workbench.security.settings import (
    SecuritySettings,
    SecuritySettingsError,
    load_settings,
    save_settings,
    settings_path,
)


@pytest.mark.parametrize("mode", list(AutonomyMode))
def test_sensitive_actions_need_approval_in_every_mode(mode: AutonomyMode) -> None:
    for category in SENSITIVE:
        assert requires_approval(mode, category), (mode, category)
    assert not requires_approval(mode, Category.READ)


def test_modes_differ_only_for_routine_work() -> None:
    assert requires_approval(AutonomyMode.ASSISTED, Category.ROUTINE)
    assert not requires_approval(AutonomyMode.SEMI_AUTONOMOUS, Category.ROUTINE)
    assert not requires_approval(AutonomyMode.CONTROLLED_AUTONOMOUS, Category.ROUTINE)


def test_every_listed_risk_of_the_spec_is_sensitive() -> None:
    expected = {
        "data_change",
        "production_write",
        "external_comment",
        "intrusive_test",
        "code_change",
        "config_change",
        "destructive_command",
        "credential_request",
        "out_of_scope",
    }
    assert {c.value for c in SENSITIVE} == expected


def test_missing_settings_mean_the_safest_defaults(tmp_path: Path) -> None:
    settings = load_settings(tmp_path)

    assert settings.mode is AutonomyMode.ASSISTED
    assert settings.allowed_hosts == () and not settings.host_allowed("https://a.test")


def test_settings_round_trip(tmp_path: Path) -> None:
    saved = SecuritySettings(
        mode=AutonomyMode.SEMI_AUTONOMOUS,
        authorized_environments=("staging",),
        allowed_hosts=("staging.example.com", ".qa.example.com"),
        max_requests_per_minute=10,
        timeout_seconds=5,
        max_retries=1,
    )

    save_settings(tmp_path, saved)

    assert load_settings(tmp_path) == saved


def test_host_matching_is_exact_or_by_dot_suffix() -> None:
    settings = SecuritySettings(
        allowed_hosts=("staging.example.com", ".qa.example.com")
    )

    assert settings.host_allowed("https://staging.example.com/x")
    assert settings.host_allowed("https://api.qa.example.com")
    assert not settings.host_allowed("https://qa.example.com")  # the suffix only
    assert not settings.host_allowed("https://evilstaging.example.com")
    assert not settings.host_allowed("https://staging.example.com.evil.test")
    assert not settings.host_allowed("not a url")


@pytest.mark.parametrize(
    "host", ["*", "*.example.com", "a.test/path", "a.test:8080", ""]
)
def test_wildcards_and_malformed_hosts_are_rejected(host: str) -> None:
    with pytest.raises(SecuritySettingsError, match="allowed host"):
        SecuritySettings(allowed_hosts=(host,))


def test_invalid_limits_are_rejected() -> None:
    with pytest.raises(SecuritySettingsError) as error:
        SecuritySettings(max_requests_per_minute=0, timeout_seconds=0, max_retries=-1)
    for text in ("max_requests_per_minute", "timeout_seconds", "max_retries"):
        assert text in str(error.value)


def test_broken_settings_files_fail_loudly(tmp_path: Path) -> None:
    path = settings_path(tmp_path)
    path.parent.mkdir(parents=True)
    for text, expected in (
        ("mode: yolo", "mode must be one of"),
        ("colour: red", "unknown setting"),
        ("- a list", "must contain a mapping"),
        ("a: [unclosed", "Cannot read"),
        ("max_retries: many", "invalid literal"),
    ):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(SecuritySettingsError, match=expected):
            load_settings(tmp_path)
