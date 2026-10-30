"""Turn a screenshot into terminal cells (half-block characters).

The TUI does not render web pages; the preview is an image drawn with one
character per two pixel rows, which works in any truecolor terminal.
"""

from pathlib import Path

from PIL import Image, UnidentifiedImageError
from rich.style import Style
from rich.text import Text

from qa_workbench.browser.errors import BrowserError


def render_halfblocks(path: Path, columns: int, rows: int) -> Text:
    """Draw the image at ``path`` inside ``columns`` x ``rows`` cells.

    The aspect ratio is kept. An unreadable image raises :class:`BrowserError`
    so the panel can show the reason instead of a blank frame.
    """
    if columns < 1 or rows < 1:
        raise ValueError("The preview area must be at least 1x1 cells.")
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise BrowserError(f"Preview frame {path} cannot be read: {error}") from error
    width, height = image.size
    scale = min(columns / width, (rows * 2) / height)
    size = (max(1, int(width * scale)), max(2, int(height * scale)))
    size = (size[0], size[1] + size[1] % 2)
    resized = image.resize(size, Image.Resampling.BILINEAR)
    pixels = resized.load()
    text = Text(no_wrap=True)
    for y in range(0, size[1], 2):
        for x in range(size[0]):
            top = pixels[x, y]
            bottom = pixels[x, y + 1]
            text.append("▀", Style(color=_hex(top), bgcolor=_hex(bottom)))
        if y + 2 < size[1]:
            text.append("\n")
    return text


def _hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)
