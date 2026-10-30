"""Wayne Industries theme tokens and shell stylesheet.

Colors communicate state, not decoration. Every color lives in ``TOKENS``;
the stylesheet refers to tokens only, so no hex value is repeated elsewhere.
Red is the institutional accent and is used sparingly: selection, focus, and
primary actions. Functional colors (success, warning, info, AI, alert) always
travel with a symbol and a name.
"""

TOKENS: dict[str, str] = {
    # Surfaces
    "gotham-black": "#0A0A0B",
    "industrial-black": "#111113",
    "batcave": "#171719",
    "dark-concrete": "#1C1C1F",
    "steel-gray": "#343438",
    # Identity
    "wayne-red": "#8F2929",
    "signal-red": "#B34A45",
    # Text
    "dirty-white": "#E5E0DC",
    "ash-gray": "#858184",
    "muted-gray": "#55545A",
    # Functional states
    "success": "#8EAD91",
    "alert": "#B34A45",
    "warning": "#E5A84B",
    "info": "#7D9EB8",
    "ai": "#A18AB8",
}

_DECLARATIONS = "\n".join(f"${name}: {value};" for name, value in TOKENS.items())

SHELL_CSS = (
    _DECLARATIONS
    + """

Screen {
    background: $gotham-black;
    color: $dirty-white;
    layout: vertical;
}

/* Header: corporate identity, discreet. */
#header {
    height: auto;
    padding: 0 1;
    background: $industrial-black;
    border-bottom: solid $steel-gray;
}

#header-row-1,
#header-row-2 {
    height: 1;
}

#header-company {
    width: 1fr;
    text-style: bold;
    color: $dirty-white;
}

#header-division,
#header-location {
    color: $ash-gray;
}

#header-division {
    width: 1fr;
}

#header-project {
    width: auto;
    color: $dirty-white;
}

#header-location {
    width: auto;
}

#body {
    height: 1fr;
}

/* Navigation: brand block above the menu. */
#navigation {
    width: 30;
    background: $industrial-black;
    border-right: solid $steel-gray;
}

#brand {
    height: auto;
    padding: 1 0 0 2;
    color: $dirty-white;
    text-style: bold;
}

#sidebar {
    height: 1fr;
    background: $industrial-black;
    padding: 0 1;
    border: none;
}

#sidebar:focus {
    border: none;
}

#navigation:focus-within {
    border-right: solid $signal-red;
}

#sidebar > .option-list--option-highlighted {
    background: $wayne-red;
    color: $dirty-white;
    text-style: bold;
}

#sidebar > .option-list--option-disabled {
    color: $ash-gray;
    text-style: bold;
}

#main {
    width: 1fr;
    padding: 1 2;
}

#page-title {
    text-style: bold;
    color: $dirty-white;
}

#page-body {
    color: $ash-gray;
    margin-top: 1;
}

#context {
    width: 30;
    background: $batcave;
    border-left: solid $steel-gray;
    padding: 1 2;
    color: $ash-gray;
}

/* Footer: identity line and status/shortcut line. */
#footer {
    height: auto;
    background: $industrial-black;
    border-top: solid $steel-gray;
    padding: 0 1;
}

#footer-identity,
#status-bar {
    height: 1;
    color: $ash-gray;
}

/* Status tones. Always paired with a symbol and a name in the text. */
.tone-success { color: $success; }
.tone-error { color: $alert; }
.tone-warning { color: $warning; }
.tone-info { color: $info; }
.tone-ai { color: $ai; }
.tone-muted { color: $ash-gray; }

.metric-panel {
    width: auto;
    min-width: 14;
    padding: 0 2;
    background: $batcave;
    border: solid $steel-gray;
    text-style: bold;
}

.detail-panel {
    padding: 1 2;
    background: $batcave;
    color: $dirty-white;
}

.state-empty,
.state-loading {
    color: $ash-gray;
    padding: 1 2;
}

.state-error {
    color: $alert;
    padding: 1 2;
    border-left: thick $alert;
}

ConfirmationDialog {
    align: center middle;
}

ConfirmationDialog > Vertical {
    width: 60;
    max-width: 90%;
    height: auto;
    padding: 1 2;
    background: $dark-concrete;
    border: solid $signal-red;
}

ConfirmationDialog #dialog-title {
    text-style: bold;
}

ConfirmationDialog #dialog-message {
    margin: 1 0;
    color: $ash-gray;
}

ConfirmationDialog Horizontal {
    height: auto;
    align-horizontal: right;
}

ConfirmationDialog Button {
    margin-left: 1;
}

/* Primary actions use Wayne Red; destructive ones use the alert color. */
Button {
    background: $dark-concrete;
    color: $dirty-white;
    border: none;
    border-top: none;
    border-bottom: none;
}

Button.-primary {
    background: $wayne-red;
    color: $dirty-white;
}

Button.-error {
    background: $alert;
    color: $gotham-black;
}

Button:focus {
    text-style: bold reverse;
}

/* Medium and narrow terminals: context opens as an overlay drawer. */
Screen.-medium #context,
Screen.-narrow #context {
    dock: right;
}

Screen.-narrow #context {
    width: 70%;
}

/* Narrow terminals: the menu takes the whole width when open. */
Screen.-narrow #navigation {
    width: 100%;
    border-right: none;
}

/* Short terminals: drop secondary identity lines and metadata. */
Screen.-short #header-row-2,
Screen.-short #footer-identity {
    display: none;
}

Screen.-short #page-body {
    margin-top: 0;
}
"""
)
