"""Metric panel: one labeled number."""

from typing import Any

from textual.widgets import Static

UNAVAILABLE = "n/a"


def format_metric(value: int | float | str | None) -> str:
    """Render a metric value. A missing value is shown as unavailable.

    Metrics must come from persisted records, so a missing value is never
    shown as zero.
    """
    if value is None:
        return UNAVAILABLE
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


class MetricPanel(Static):
    """Shows a label above its value."""

    def __init__(
        self, label: str, value: int | float | str | None, **kwargs: Any
    ) -> None:
        if not label.strip():
            raise ValueError("MetricPanel needs a label.")
        self._heading = label.strip().upper()
        super().__init__(f"{self._heading}\n{format_metric(value)}", **kwargs)
        self.add_class("metric-panel")

    def set_value(self, value: int | float | str | None) -> None:
        self.update(f"{self._heading}\n{format_metric(value)}")
