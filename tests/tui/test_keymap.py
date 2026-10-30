import pytest

from qa_workbench.tui.keymap import Keymap, KeymapError, display_key, normalize_key


def test_default_keymap_has_no_conflicts() -> None:
    keymap = Keymap.default()

    keys = [shortcut.key for shortcut in keymap.shortcuts]
    assert len(keys) == len(set(keys))


def test_default_shortcuts_follow_the_visual_spec() -> None:
    keymap = Keymap.default()

    assert keymap.key_for("command_palette") == "ctrl+p"
    assert keymap.key_for("focus_search") == "ctrl+k"
    assert keymap.key_for("go_back") == "escape"
    assert keymap.key_for("help") == "question_mark"


def test_overrides_replace_only_the_named_actions() -> None:
    keymap = Keymap.from_overrides({"toggle_context": "F3"})

    assert keymap.key_for("toggle_context") == "f3"
    assert keymap.key_for("toggle_sidebar") == "f1"


def test_user_friendly_key_names_are_accepted() -> None:
    keymap = Keymap.from_overrides({"help": "?", "go_back": "Esc"})

    assert keymap.key_for("help") == "question_mark"
    assert keymap.key_for("go_back") == "escape"


def test_unknown_action_is_rejected_with_valid_names() -> None:
    with pytest.raises(KeymapError, match="Unknown shortcut action") as error:
        Keymap.from_overrides({"teleport": "f9"})

    assert "toggle_sidebar" in str(error.value)


def test_conflicting_keys_name_both_actions() -> None:
    with pytest.raises(KeymapError, match=r"F1 is assigned to both") as error:
        Keymap.from_overrides({"toggle_context": "f1"})

    assert "toggle_sidebar" in str(error.value)
    assert "toggle_context" in str(error.value)


@pytest.mark.parametrize("key", ["ctrl+c", "Ctrl+Z", "ctrl+s"])
def test_terminal_reserved_keys_are_rejected(key: str) -> None:
    with pytest.raises(KeymapError, match="reserved by the terminal"):
        Keymap.from_overrides({"help": key})


def test_blank_key_is_rejected() -> None:
    with pytest.raises(KeymapError, match="cannot be empty"):
        Keymap.from_overrides({"help": "  "})


def test_key_for_unknown_action_fails() -> None:
    with pytest.raises(KeyError, match="Unknown shortcut action"):
        Keymap.default().key_for("nope")


def test_bindings_cover_every_shortcut() -> None:
    keymap = Keymap.default()

    bindings = keymap.bindings()

    assert [b.action for b in bindings] == [s.action for s in keymap.shortcuts]
    assert [b.key for b in bindings] == [s.key for s in keymap.shortcuts]


def test_help_bar_uses_the_effective_keys() -> None:
    keymap = Keymap.from_overrides({"command_palette": "ctrl+o"})

    assert "Ctrl+O Palette" in keymap.help_bar()
    assert "? Help" in keymap.help_bar()


def test_help_text_lists_every_shortcut() -> None:
    text = Keymap.default().help_text()

    assert len(text.splitlines()) == len(Keymap.default().shortcuts)
    assert "Ctrl+P" in text
    assert "Esc" in text


@pytest.mark.parametrize(
    ("key", "expected"),
    [("ctrl+k", "Ctrl+K"), ("f1", "F1"), ("escape", "Esc"), ("question_mark", "?")],
)
def test_display_key(key: str, expected: str) -> None:
    assert display_key(key) == expected


def test_normalize_key_lowercases_and_strips() -> None:
    assert normalize_key("  Ctrl+K ") == "ctrl+k"
