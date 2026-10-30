"""Command palette provider for the workbench."""

from functools import partial
from typing import TYPE_CHECKING

from textual.command import DiscoveryHit, Hit, Hits, Provider

from qa_workbench.tui.palette import PaletteEntry

if TYPE_CHECKING:
    from qa_workbench.tui.app import WorkbenchApp


class WorkbenchCommands(Provider):
    """Offers destinations and actions, searched by fuzzy match."""

    @property
    def _app(self) -> "WorkbenchApp":
        return self.app  # type: ignore[return-value]

    def _callback(self, entry: PaletteEntry):  # noqa: ANN202
        return partial(self._app.run_palette_action, entry.action)

    async def discover(self) -> Hits:
        for entry in self._app.palette_entries():
            yield DiscoveryHit(entry.title, self._callback(entry), help=entry.help)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for entry in self._app.palette_entries():
            score = matcher.match(entry.title)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(entry.title),
                    self._callback(entry),
                    help=entry.help,
                )
