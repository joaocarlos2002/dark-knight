"""Atomic file writes."""

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text so readers never see a partial file.

    Newlines are written as given (never converted to CRLF on Windows). The
    text goes to a temporary file in the same folder and then replaces the
    target in one step.
    """
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
