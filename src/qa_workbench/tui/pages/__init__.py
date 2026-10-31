"""The pages of the workbench, by navigation key."""

import importlib
import pkgutil

from qa_workbench.tui.pages.base import Page, PageContext
from qa_workbench.tui.pages.registry import PAGES, register

# Importing a module registers its page.
for _module in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_module.name}")

__all__ = ["PAGES", "Page", "PageContext", "register"]
