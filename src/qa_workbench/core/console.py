"""Console output that survives the platform's default encoding."""

import sys
from typing import TextIO


def ensure_utf8_output(streams: tuple[TextIO, ...] | None = None) -> None:
    """Make stdout and stderr write UTF-8.

    On Windows, output that is piped or redirected uses the legacy code page, and
    printing a status symbol such as the check mark then fails. Reports and
    statuses use such symbols on purpose (names and symbols, not color alone), so
    the CLI writes UTF-8 and replaces what a stream still cannot hold rather than
    crashing.
    """
    for stream in streams if streams is not None else (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None or encoding == "utf8":
            continue
        reconfigure(encoding="utf-8", errors="replace")
