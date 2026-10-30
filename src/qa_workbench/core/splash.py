"""Optional cinematic startup splash for the workbench."""

from __future__ import annotations

import logging
import random
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from qa_workbench.core.config import AppConfig
from qa_workbench.edits.service import find_edits

logger = logging.getLogger(__name__)

TERMINAL_TITLES = (
    "alacritty",
    "cmd",
    "command prompt",
    "conhost",
    "cursor",
    "hyper",
    "kitty",
    "mintty",
    "powershell",
    "pwsh",
    "tabby",
    "terminal",
    "visual studio code",
    "warp",
    "wezterm",
)
SW_MINIMIZE = 6
SW_RESTORE = 9


def choose_edit(edits: Sequence[Path], rng: random.Random | None = None) -> Path | None:
    """Pick one edit at random, or return None when there are none."""
    if not edits:
        return None
    return (rng or random.SystemRandom()).choice(list(edits))


def find_player() -> str | None:
    """Find a video player that can play fullscreen without controls."""
    for name in ("mpv", "ffplay", "vlc"):
        player = shutil.which(name)
        if player is not None:
            return player
    return None


def player_command(player: str, video: Path) -> list[str]:
    """Build the command that plays *video* without a visible player."""
    name = Path(player).stem.lower()
    if name == "mpv":
        return [
            player,
            "--fullscreen",
            "--no-border",
            "--no-osc",
            "--no-osd-bar",
            "--no-input-default-bindings",
            "--really-quiet",
            "--no-terminal",
            "--title=DARK KNIGHT QA",
            str(video),
        ]
    if name == "vlc":
        return [
            player,
            "--fullscreen",
            "--no-video-title-show",
            "--play-and-exit",
            "--intf",
            "dummy",
            "--quiet",
            str(video),
        ]
    return [
        player,
        "-fs",
        "-autoexit",
        "-noborder",
        "-alwaysontop",
        "-exitonkeydown",
        "-exitonmousedown",
        "-hide_banner",
        "-loglevel",
        "quiet",
        "-window_title",
        "DARK KNIGHT QA",
        str(video),
    ]


def play_startup_splash(
    config: AppConfig,
    *,
    interactive: bool | None = None,
    runner: Callable[..., object] = subprocess.run,
) -> Path | None:
    """Play a random edit fullscreen before the workbench starts.

    Returns the edit that was played, or None when the splash was skipped.
    Playback failures never stop the workbench from starting.
    """
    if not config.splash_enabled:
        return None
    if interactive is None:
        interactive = is_interactive()
    if not interactive:
        return None
    video = choose_edit(find_edits(config.edits_dir))
    if video is None:
        return None
    player = config.splash_player or find_player()
    if player is None:
        logger.warning(
            "No video player found for the startup splash; install ffplay or mpv."
        )
        return None

    logger.info("Playing startup splash: %s", video)
    handle = _hide_terminal()
    try:
        runner(
            player_command(player, video),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, KeyboardInterrupt) as error:
        logger.debug("Startup splash stopped early: %s", error)
    finally:
        _restore_terminal(handle)
    return video


def is_interactive() -> bool:
    try:
        return bool(sys.stdout and sys.stdout.isatty())
    except (AttributeError, OSError):
        return False


def _hide_terminal() -> int | None:
    """Minimize the terminal window so the desktop shows behind the video."""
    handle = _terminal_window()
    if handle is None:
        return None
    try:
        import ctypes

        ctypes.windll.user32.ShowWindow(handle, SW_MINIMIZE)
    except Exception:
        return None
    return handle


def _restore_terminal(handle: int | None) -> None:
    if handle is None or sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.ShowWindow(handle, SW_RESTORE)
        user32.SetForegroundWindow(handle)
    except Exception:
        pass


def _terminal_window() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        console = kernel32.GetConsoleWindow()
        if console and user32.IsWindowVisible(console):
            return int(console)
        if not console:
            return None
        foreground = user32.GetForegroundWindow()
        if not foreground:
            return None
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(foreground, title, 256)
        if any(token in title.value.lower() for token in TERMINAL_TITLES):
            return int(foreground)
    except Exception:
        return None
    return None
