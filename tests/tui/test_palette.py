from qa_workbench.tui import navigation
from qa_workbench.tui.keymap import Keymap
from qa_workbench.tui.palette import GO_PREFIX, destination_key, palette_entries


def test_every_destination_is_reachable_from_the_palette() -> None:
    entries = palette_entries(Keymap.default())

    destinations = {
        destination_key(entry.action)
        for entry in entries
        if destination_key(entry.action) is not None
    }
    assert destinations == {item.key for item in navigation.all_items()}


def test_destination_entries_say_where_they_go() -> None:
    entries = palette_entries(Keymap.default())

    overview = next(e for e in entries if e.action == f"{GO_PREFIX}overview")
    assert overview.title == "Go to Overview"
    assert overview.help == "Workspace"


def test_actions_show_their_current_shortcut() -> None:
    keymap = Keymap.from_overrides({"toggle_context": "f3"})

    entries = palette_entries(keymap)

    toggle = next(e for e in entries if e.action == "toggle_context")
    assert toggle.help == "Shortcut: F3"


def test_palette_and_back_are_not_offered_as_commands() -> None:
    actions = {entry.action for entry in palette_entries(Keymap.default())}

    assert "command_palette" not in actions
    assert "go_back" not in actions


def test_destination_key_ignores_plain_actions() -> None:
    assert destination_key("quit") is None
    assert destination_key("go:reports") == "reports"
