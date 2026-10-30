"""Dark theme tokens and shell stylesheet.

Colors communicate state, not decoration. Tokens are semantic so screens
never hard-code hex values.
"""

TOKENS: dict[str, str] = {
    "background": "#101216",
    "surface": "#171B22",
    "elevated": "#202631",
    "border": "#303846",
    "text": "#E6EAF0",
    "text-muted": "#A0A9B8",
    "text-disabled": "#687386",
    "accent": "#6EA8FE",
    "info": "#56B6C2",
    "success": "#69C58B",
    "warning": "#E5B567",
    "error": "#E57373",
    "ai": "#B392F0",
}

_DECLARATIONS = "\n".join(f"${name}: {value};" for name, value in TOKENS.items())

SHELL_CSS = (
    _DECLARATIONS
    + """

Screen {
    background: $background;
    color: $text;
    layout: vertical;
}

#header {
    height: 1;
    padding: 0 1;
    background: $surface;
    color: $text;
    text-style: bold;
}

#header-title {
    width: auto;
}

#header-project {
    width: 1fr;
    text-align: right;
    color: $text-muted;
}

#body {
    height: 1fr;
}

#sidebar {
    width: 26;
    background: $surface;
    border-right: solid $border;
    padding: 0 1;
}

#sidebar:focus {
    border-right: solid $accent;
}

#sidebar > .option-list--option-highlighted {
    background: $elevated;
    color: $accent;
    text-style: bold;
}

#sidebar > .option-list--option-disabled {
    color: $text-muted;
    text-style: bold;
}

#main {
    width: 1fr;
    padding: 1 2;
}

#page-title {
    text-style: bold;
    color: $text;
}

#page-body {
    color: $text-muted;
    margin-top: 1;
}

#context {
    width: 32;
    background: $surface;
    border-left: solid $border;
    padding: 1 2;
    color: $text-muted;
}

#status-bar {
    height: 1;
    padding: 0 1;
    background: $elevated;
    color: $text-muted;
}

/* Status tones. Always paired with a symbol and a name in the text. */
.tone-success { color: $success; }
.tone-error { color: $error; }
.tone-warning { color: $warning; }
.tone-info { color: $info; }
.tone-ai { color: $ai; }
.tone-muted { color: $text-muted; }

.metric-panel {
    width: auto;
    min-width: 14;
    padding: 0 2;
    background: $surface;
    border: solid $border;
    text-style: bold;
}

.detail-panel {
    padding: 1 2;
    background: $surface;
    color: $text;
}

.state-empty,
.state-loading {
    color: $text-muted;
    padding: 1 2;
}

.state-error {
    color: $error;
    padding: 1 2;
    border-left: thick $error;
}

ConfirmationDialog {
    align: center middle;
}

ConfirmationDialog > Vertical {
    width: 60;
    max-width: 90%;
    height: auto;
    padding: 1 2;
    background: $elevated;
    border: solid $accent;
}

ConfirmationDialog #dialog-title {
    text-style: bold;
}

ConfirmationDialog #dialog-message {
    margin: 1 0;
    color: $text-muted;
}

ConfirmationDialog Horizontal {
    height: auto;
    align-horizontal: right;
}

ConfirmationDialog Button {
    margin-left: 1;
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
Screen.-narrow #sidebar {
    width: 100%;
    border-right: none;
}

/* Short terminals: drop secondary metadata. */
Screen.-short #page-body {
    margin-top: 0;
}
"""
)
