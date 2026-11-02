"""The pages of the workbench, by navigation key."""

import importlib
import pkgutil

from qa_workbench.tui import navigation
from qa_workbench.tui.pages.base import Page, PageContext
from qa_workbench.tui.pages.registry import (
    PAGES,
    register,
    screen_contracts,
    validate_screen_contracts,
)

# Importing a module registers its page.
for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")

validate_screen_contracts({item.key for item in navigation.all_items()})

__all__ = [
    "PAGES",
    "Page",
    "PageContext",
    "register",
    "screen_contracts",
]
