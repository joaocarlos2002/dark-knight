import pytest

from qa_workbench.tui.navigation import DEFAULT_KEY, all_items, find_item


def test_navigation_keys_are_unique() -> None:
    keys = [item.key for item in all_items()]

    assert len(keys) == len(set(keys))


def test_default_destination_exists() -> None:
    assert find_item(DEFAULT_KEY).title == "Overview"


def test_unknown_destination_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown navigation destination"):
        find_item("nowhere")
