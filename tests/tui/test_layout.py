import pytest

from qa_workbench.tui.layout import WidthClass, classify_width, layout_for


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        (200, WidthClass.WIDE),
        (120, WidthClass.WIDE),
        (119, WidthClass.MEDIUM),
        (80, WidthClass.MEDIUM),
        (79, WidthClass.NARROW),
        (1, WidthClass.NARROW),
    ],
)
def test_width_breakpoints(columns: int, expected: WidthClass) -> None:
    assert classify_width(columns) is expected


def test_wide_layout_shows_every_region() -> None:
    layout = layout_for(140, 40)

    assert layout.sidebar_visible
    assert layout.context_visible
    assert not layout.short


def test_medium_layout_hides_context_by_default() -> None:
    layout = layout_for(100, 40)

    assert layout.sidebar_visible
    assert not layout.context_visible


def test_narrow_layout_shows_content_only() -> None:
    layout = layout_for(60, 40)

    assert not layout.sidebar_visible
    assert not layout.context_visible


def test_short_terminal_is_flagged() -> None:
    assert layout_for(140, 23).short
    assert not layout_for(140, 24).short


@pytest.mark.parametrize(("columns", "rows"), [(0, 30), (-5, 30), (100, 0), (100, -1)])
def test_non_positive_size_is_rejected(columns: int, rows: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        layout_for(columns, rows)
