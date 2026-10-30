import pytest
from fake_ai import FakeProvider

from qa_workbench.ai.errors import NoProviderAvailable
from qa_workbench.ai.selection import select_engine


def _factory(available: bool, name: str):
    provider = FakeProvider([], name=name, available=available)
    return lambda: (provider, object())


def test_a_specific_mode_never_falls_back_to_another_engine() -> None:
    factories = {"own": _factory(False, "own"), "opencode": _factory(True, "oc")}

    with pytest.raises(NoProviderAvailable, match="own: down"):
        select_engine("own", factories)
    assert select_engine("opencode", factories).mode == "opencode"


def test_auto_prefers_own_then_opencode() -> None:
    both = {"own": _factory(True, "own"), "opencode": _factory(True, "oc")}
    only_oc = {"own": _factory(False, "own"), "opencode": _factory(True, "oc")}

    assert select_engine("auto", both).mode == "own"
    assert select_engine("auto", only_oc).mode == "opencode"


def test_nothing_available_lists_every_reason() -> None:
    factories = {"own": _factory(False, "own"), "opencode": _factory(False, "oc")}

    with pytest.raises(NoProviderAvailable) as error:
        select_engine("auto", factories)
    assert "own: down" in str(error.value) and "opencode: down" in str(error.value)


def test_missing_factory_and_bad_mode_are_explicit() -> None:
    with pytest.raises(NoProviderAvailable, match="not configured"):
        select_engine("opencode", {})
    with pytest.raises(ValueError, match="mode must be one of"):
        select_engine("magic", {})
