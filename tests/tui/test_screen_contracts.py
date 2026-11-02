"""Focused tests for the TUI navigation and screen implementation contract."""

import asyncio

import pytest

from qa_workbench.tui import navigation
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.pages import PAGES, screen_contracts
from qa_workbench.tui.pages.registry import (
    SHELL_ONLY_PAGES,
    validate_screen_contracts,
)


def test_every_navigable_screen_has_one_implementation_contract() -> None:
    navigation_keys = {item.key for item in navigation.all_items()}
    validate_screen_contracts(navigation_keys)

    contracts = screen_contracts()
    assert set(contracts) == navigation_keys - SHELL_ONLY_PAGES
    assert all(contract.page_class in PAGES.values() for contract in contracts.values())


def test_browser_pages_expose_the_shared_browse_contract() -> None:
    browser_contracts = [
        contract
        for contract in screen_contracts().values()
        if contract.supports_search
    ]

    assert browser_contracts
    assert all(contract.supports_filter for contract in browser_contracts)
    assert all(contract.supports_detail for contract in browser_contracts)


@pytest.mark.parametrize("size", [(140, 40), (90, 40), (60, 20)])
def test_every_implemented_screen_mounts_at_supported_terminal_sizes(
    size: tuple[int, int],
) -> None:
    async def runner() -> None:
        app = WorkbenchApp()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            for key in PAGES:
                app.navigate(key)
                await pilot.pause()
                assert app._page_for(key) is not None
                assert app._page_for(key).display

    asyncio.run(runner())
