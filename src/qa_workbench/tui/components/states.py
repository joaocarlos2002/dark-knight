"""Empty, loading, and error states."""

from typing import Any

from textual.widgets import Static

from qa_workbench.i18n import tr
from qa_workbench.tui.status import Status, format_status


class EmptyState(Static):
    """Explains that there is nothing to show yet and what to do next."""

    def __init__(self, message: str, hint: str = "", **kwargs: Any) -> None:
        if not message.strip():
            raise ValueError("EmptyState needs a message.")
        text = f"{tr(message)}\n{tr(hint)}" if hint else tr(message)
        super().__init__(text, **kwargs)
        self.add_class("state-empty")


class LoadingState(Static):
    """Static loading indicator. It does not rely on animation."""

    def __init__(self, message: str = "Loading", **kwargs: Any) -> None:
        super().__init__(f"{format_status(Status.RUNNING)}  {tr(message)}", **kwargs)
        self.add_class("state-loading")


class ErrorState(Static):
    """A recoverable failure, with the diagnostic context needed to act on it.

    A failure is always shown as a failure; it is never replaced by an empty
    or successful-looking view.
    """

    def __init__(self, title: str, detail: str, hint: str = "", **kwargs: Any):
        if not title.strip() or not detail.strip():
            raise ValueError("ErrorState needs a title and a detail.")
        lines = [f"{format_status(Status.FAILED)}  {tr(title)}", tr(detail)]
        if hint:
            lines.append(f"{tr('Next step')}: {tr(hint)}")
        super().__init__("\n".join(lines), **kwargs)
        self.add_class("state-error")
