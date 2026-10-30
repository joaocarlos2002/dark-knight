"""Terminal size classification for the responsive shell."""

from dataclasses import dataclass
from enum import Enum

WIDE_MIN_COLUMNS = 100
MEDIUM_MIN_COLUMNS = 80
SHORT_MAX_ROWS = 24


class WidthClass(Enum):
    """How much horizontal space the terminal offers."""

    WIDE = "wide"
    MEDIUM = "medium"
    NARROW = "narrow"


@dataclass(frozen=True)
class ShellLayout:
    """Which shell regions are visible for a terminal size."""

    width_class: WidthClass
    short: bool
    sidebar_visible: bool
    context_visible: bool


def classify_width(columns: int) -> WidthClass:
    """Classify a terminal width in columns."""
    if columns <= 0:
        raise ValueError(f"Terminal width must be positive, got {columns}.")
    if columns >= WIDE_MIN_COLUMNS:
        return WidthClass.WIDE
    if columns >= MEDIUM_MIN_COLUMNS:
        return WidthClass.MEDIUM
    return WidthClass.NARROW


def layout_for(columns: int, rows: int) -> ShellLayout:
    """Return the default region visibility for a terminal size.

    Wide terminals show every region. Medium terminals keep navigation and
    content, with context available on demand. Narrow terminals show content
    only, with navigation available on demand.
    """
    if rows <= 0:
        raise ValueError(f"Terminal height must be positive, got {rows}.")
    width_class = classify_width(columns)
    return ShellLayout(
        width_class=width_class,
        short=rows < SHORT_MAX_ROWS,
        sidebar_visible=width_class is not WidthClass.NARROW,
        context_visible=width_class is WidthClass.WIDE,
    )
