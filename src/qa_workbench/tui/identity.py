"""Product identity text shown in the shell chrome.

Text only: no logos or protected symbols are used as product identity.
"""

from qa_workbench.tui.status import Status, style_for

COMPANY = "WAYNE INDUSTRIES"
DIVISION = "ADVANCED TECHNOLOGY DIVISION"
PRODUCT = "DARK KNIGHT QA"
TAGLINE = "QUALITY INTELLIGENCE SYSTEM"
LOCATION = "INTERNAL SYSTEM / GOTHAM CITY"

NO_PROJECT_HEADER = "NO PROJECT"
NO_PROJECT_FOOTER = "No project"


def brand_text() -> str:
    """Product name and tagline shown above the navigation menu."""
    return f"{PRODUCT}\n{TAGLINE}"


def footer_identity_text(operational: Status = Status.READY) -> str:
    """Corporate footer line with a symbol-and-name system status."""
    symbol = style_for(operational).symbol
    return (
        f"{COMPANY} / INTERNAL SOFTWARE │ AUTHORIZED ACCESS ONLY │ "
        f"SYSTEM STATUS: {symbol} OPERATIONAL"
    )
