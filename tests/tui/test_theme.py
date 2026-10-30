import re

from qa_workbench.tui.theme import SHELL_CSS, TOKENS

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")


def _luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(foreground: str, background: str) -> float:
    """WCAG contrast ratio between two ``#RRGGBB`` colors."""
    lighter, darker = sorted(
        (_luminance(TOKENS.get(foreground, foreground)), _luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


def test_every_token_is_a_six_digit_hex_color() -> None:
    assert all(HEX.fullmatch(value) for value in TOKENS.values())


def test_hex_values_live_only_in_the_token_block() -> None:
    declarations = "\n".join(f"${name}: {value};" for name, value in TOKENS.items())
    stylesheet = SHELL_CSS.removeprefix(declarations)

    assert HEX.findall(stylesheet) == []


def test_every_variable_used_by_the_stylesheet_is_defined() -> None:
    used = set(re.findall(r"\$([a-z-]+)", SHELL_CSS.split("Screen {", 1)[1]))

    assert used <= set(TOKENS)


def test_main_background_is_gotham_black() -> None:
    assert TOKENS["gotham-black"] == "#0A0A0B"
    assert "background: $gotham-black;" in SHELL_CSS


def test_primary_text_is_readable_on_every_surface() -> None:
    for surface in ("gotham-black", "industrial-black", "batcave", "dark-concrete"):
        assert contrast("dirty-white", TOKENS[surface]) >= 7.0, surface


def test_secondary_text_is_readable_on_every_surface() -> None:
    for surface in ("gotham-black", "industrial-black", "batcave"):
        assert contrast("ash-gray", TOKENS[surface]) >= 4.5, surface


def test_functional_colors_are_readable_on_the_background() -> None:
    background = TOKENS["gotham-black"]

    for name in ("success", "warning", "info", "ai"):
        assert contrast(name, background) >= 4.5, name


def test_alert_color_meets_the_ui_component_minimum() -> None:
    # Alert is always paired with a symbol and a label (never color alone), so
    # the WCAG minimum for UI components (3:1) applies rather than 4.5:1.
    assert contrast("alert", TOKENS["gotham-black"]) >= 3.0


def test_red_is_reserved_for_identity_and_alerts() -> None:
    reds = {name for name, value in TOKENS.items() if value in {"#8F2929", "#B34A45"}}

    assert reds == {"wayne-red", "signal-red", "alert"}
