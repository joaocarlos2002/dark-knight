import pytest

from qa_workbench.tui.navigation import DEFAULT_KEY, SECTIONS, all_items, find_item


def test_navigation_keys_are_unique() -> None:
    keys = [item.key for item in all_items()]

    assert len(keys) == len(set(keys))


def test_default_destination_exists() -> None:
    assert find_item(DEFAULT_KEY).title == "Overview"


def test_unknown_destination_is_rejected() -> None:
    with pytest.raises(KeyError, match="Unknown navigation destination"):
        find_item("nowhere")


def test_sections_follow_the_visual_specification() -> None:
    assert [section.title for section in SECTIONS] == [
        "WORKSPACE",
        "OPERATIONS",
        "INTELLIGENCE",
    ]
    assert [item.title for item in all_items()] == [
        "Overview",
        "Requirements",
        "Test Cases",
        "Test Plans",
        "Test Suites",
        "Executions",
        "Browser Preview",
        "Bug Hunting",
        "API Testing",
        "Security",
        "AI Agent",
        "Release Analysis",
        "Pipelines",
        "Knowledge Base",
    ]
