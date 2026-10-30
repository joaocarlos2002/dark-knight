"""Detail panel: labeled fields for the selected item."""

from collections.abc import Sequence
from typing import Any

from textual.widgets import Static

EMPTY_VALUE = "-"


def format_fields(fields: Sequence[tuple[str, str]]) -> str:
    """Align ``label  value`` rows. Blank values are shown as ``-``."""
    if not fields:
        return ""
    width = max(len(label) for label, _ in fields)
    return "\n".join(
        f"{label:<{width}}  {value.strip() or EMPTY_VALUE}" for label, value in fields
    )


class DetailPanel(Static):
    """Shows a title and the fields of one item."""

    def __init__(
        self, title: str, fields: Sequence[tuple[str, str]], **kwargs: Any
    ) -> None:
        if not title.strip():
            raise ValueError("DetailPanel needs a title.")
        self._heading = title.strip().upper()
        super().__init__(self._compose_text(fields), **kwargs)
        self.add_class("detail-panel")

    def set_fields(self, fields: Sequence[tuple[str, str]]) -> None:
        self.update(self._compose_text(fields))

    def _compose_text(self, fields: Sequence[tuple[str, str]]) -> str:
        return f"{self._heading}\n\n{format_fields(fields)}".rstrip()
