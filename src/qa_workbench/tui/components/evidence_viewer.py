"""EvidenceViewer: display an EVD record with verification and preview."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from qa_workbench.browser.render import render_halfblocks
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import Record
from qa_workbench.tui.components.states import EmptyState, ErrorState
from qa_workbench.tui.status import Status, format_status


@dataclass(frozen=True)
class EvidenceViewData:
    """Prepared data for rendering an evidence record."""

    record: Record
    file_path: Path | None
    problems: list[str]
    is_intact: bool
    content_preview: str | None
    media_type: str
    size: int
    sha256: str
    source: str
    description: str
    execution: str | None
    step: str | None
    source_url: str | None
    derived_from: str | None
    captured_at: str | None


def prepare_evidence_data(
    store: EvidenceStore, evidence_id: str
) -> EvidenceViewData | None:
    """Read an evidence record and prepare its view data.

    Returns ``None`` if the record does not exist or cannot be read.
    """
    try:
        record = store.get(evidence_id)
    except Exception:
        return None

    meta = record.metadata
    problems = store.verify(evidence_id)
    is_intact = len(problems) == 0

    file_path: Path | None = None
    try:
        file_path = store.file_path(record)
    except Exception:
        pass

    content_preview: str | None = None
    if file_path and file_path.is_file():
        media_type = meta.get("media_type", "application/octet-stream")
        if media_type.startswith("text/") or media_type in {
            "application/json",
            "application/x-yaml",
        }:
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
                content_preview = "\n".join(text.splitlines()[:50])
            except Exception:
                content_preview = "(cannot read as text)"

    return EvidenceViewData(
        record=record,
        file_path=file_path,
        problems=problems,
        is_intact=is_intact,
        content_preview=content_preview,
        media_type=meta.get("media_type", "application/octet-stream"),
        size=meta.get("size", 0),
        sha256=meta.get("sha256", ""),
        source=meta.get("source", ""),
        description=meta.get("description", ""),
        execution=meta.get("execution"),
        step=meta.get("step"),
        source_url=meta.get("source_url"),
        derived_from=meta.get("derived_from"),
        captured_at=meta.get("captured_at"),
    )


class EvidenceViewer(Vertical):
    """A widget that shows a single evidence record with verification status."""

    def __init__(self, data: EvidenceViewData | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._data = data
        self.add_class("evidence-viewer")

    def set_data(self, data: EvidenceViewData | None) -> None:
        """Update the displayed evidence."""
        self._data = data
        self._refresh()

    def _refresh(self) -> None:
        self.remove_children()
        self.mount(*self._compose_children())

    def _compose_children(self) -> list:
        if self._data is None:
            return [EmptyState("No evidence selected.", "Choose one from the list.")]

        data = self._data
        meta = data.record.metadata
        children: list = []

        # Header with integrity status
        if data.is_intact:
            status = format_status(Status.PASSED)
            status_text = "INTEGRITY VERIFIED"
        else:
            status = format_status(Status.FAILED)
            status_text = "INTEGRITY PROBLEM"

        header = f"{status}  {data.record.id}  {status_text}"
        children.append(Static(header, id="evidence-header", markup=False))

        # Metadata fields
        lines = [
            f"File          {data.record.id}/{meta.get('original_name', 'unknown')}",
            f"SHA-256       {data.sha256}",
            f"Size          {data.size} bytes",
            f"Media type    {data.media_type}",
            f"Source        {data.source}",
            f"Description   {data.description}",
        ]
        if data.execution:
            lines.append(f"Execution     {data.execution}")
        if data.step:
            lines.append(f"Step          {data.step}")
        if data.source_url:
            lines.append(f"Source URL    {data.source_url}")
        if data.derived_from:
            lines.append(f"Derived from  {data.derived_from}")
        if data.captured_at:
            lines.append(f"Captured at   {data.captured_at}")

        children.append(Static("\n".join(lines), id="evidence-meta", markup=False))

        # Problems
        if data.problems:
            prob_lines = ["INTEGRITY PROBLEMS:", *[f"  - {p}" for p in data.problems]]
            children.append(
                Static("\n".join(prob_lines), id="evidence-problems", markup=False)
            )

        # Content preview or image
        if data.content_preview is not None:
            children.append(
                Static("CONTENT PREVIEW (first 50 lines):", classes="section-title")
            )
            children.append(
                Static(data.content_preview, id="evidence-preview", markup=False)
            )
        elif data.file_path and data.file_path.is_file():
            media_type = data.media_type
            if media_type.startswith("image/"):
                children.append(Static("IMAGE PREVIEW:", classes="section-title"))
                # We'll render the image in on_mount when we know the size
                children.append(Static("", id="evidence-image", markup=False))
            else:
                children.append(
                    EmptyState(
                        "Binary file; no text preview available.",
                        f"Type: {media_type}, Size: {data.size} bytes",
                    )
                )
        else:
            children.append(ErrorState("Evidence file not found on disk."))

        return children

    def on_mount(self) -> None:
        self._refresh()
        # If we have an image, render it after layout
        if self._data and self._data.file_path:
            self.call_later(self._render_image_if_needed)

    def _render_image_if_needed(self) -> None:
        data = self._data
        if not data or not data.file_path or not data.file_path.is_file():
            return
        media_type = data.media_type
        if not media_type.startswith("image/"):
            return
        try:
            image_widget = self.query_one("#evidence-image", Static)
            # Get the available width from the widget
            width = image_widget.size.width
            if width < 10:
                return
            # Use a reasonable height
            height = min(30, max(10, image_widget.size.height or 20))
            text = render_halfblocks(data.file_path, width, height)
            image_widget.update(text)
        except Exception:
            pass


class EvidenceListRow(Static):
    """A single row in the evidence list."""

    def __init__(
        self,
        evidence_id: str,
        description: str,
        source: str,
        size: int,
        is_intact: bool,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.evidence_id = evidence_id
        status = (
            format_status(Status.PASSED) if is_intact else format_status(Status.FAILED)
        )
        size_str = f"{size} B" if size < 1024 else f"{size // 1024} KB"
        self.update(
            f"{status}  {evidence_id}  {description[:60]}  ({source}, {size_str})"
        )
        self.add_class("evidence-list-row")


class EvidenceList(VerticalScroll):
    """A scrollable list of evidence records."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_class("evidence-list")
        self._store: EvidenceStore | None = None

    def set_store(self, store: EvidenceStore) -> None:
        self._store = store
        self.refresh_list()

    def refresh_list(self) -> None:
        self.remove_children()
        if self._store is None:
            self.mount(
                EmptyState("No project open.", "Open a project to see evidence.")
            )
            return

        listing = self._store.list_records()
        if not listing.records:
            self.mount(
                EmptyState(
                    "No evidence registered.",
                    "Add evidence with `batman evidence add`.",
                )
            )
            return

        for record in listing.records:
            meta = record.metadata
            problems = self._store.verify(record.id)
            is_intact = len(problems) == 0
            self.mount(
                EvidenceListRow(
                    record.id,
                    str(meta.get("description", "")),
                    str(meta.get("source", "")),
                    int(meta.get("size", 0)),
                    is_intact,
                )
            )
