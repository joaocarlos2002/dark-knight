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
