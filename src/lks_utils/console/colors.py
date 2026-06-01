"""
ANSI color definitions and text styling utilities.

Provides cross-platform color support with automatic detection of terminal
capabilities. Falls back to plain text when colors are not supported.

Usage:
    from lks_utils.console.colors import LogLevel, style_text
    
    styled = style_text("Hello", LogLevel.SUCCESS)
    print(styled)  # Prints green "Hello" in capable terminals
"""

from __future__ import annotations

import os
import re
import sys
from enum import Enum


# ANSI escape code constants
RESET: str = "\033[0m"
BOLD: str = "\033[1m"
DIM: str = "\033[2m"
ITALIC: str = "\033[3m"
UNDERLINE: str = "\033[4m"

# Global color state
_color_enabled: bool | None = None


class LogLevel(str, Enum):
    """Log level styles with associated ANSI colors."""

    DEBUG = "\033[90m"      # Gray
    INFO = "\033[0m"        # Default (no color)
    WARN = "\033[93m"       # Yellow
    ERROR = "\033[91m"      # Red
    SUCCESS = "\033[92m"    # Green

    def __str__(self) -> str:
        return self.value


class SemanticColor(str, Enum):
    """Semantic color definitions for various UI purposes."""

    # Status colors
    SUCCESS = "\033[92m"    # Green
    WARNING = "\033[93m"    # Yellow
    ERROR = "\033[91m"      # Red
    INFO = "\033[94m"       # Blue

    # Semantic colors
    HIGHLIGHT = "\033[96m"  # Cyan
    MUTED = "\033[90m"      # Gray
    PRIMARY = "\033[97m"    # White (bright)
    SECONDARY = "\033[37m"  # Light gray

    # Data colors
    NUMBER = "\033[95m"     # Magenta
    PATH = "\033[36m"       # Cyan
    TIMESTAMP = "\033[90m"  # Gray

    # Performance colors
    FAST = "\033[92m"       # Green
    MEDIUM = "\033[93m"     # Yellow
    SLOW = "\033[91m"       # Red

    def __str__(self) -> str:
        return self.value


def supports_color() -> bool:
    """
    Detect if the current terminal supports ANSI colors.

    Checks:
    - NO_COLOR environment variable (https://no-color.org/)
    - LKS_CONSOLE_COLOR environment variable
    - Windows legacy terminal detection
    - TTY detection

    Returns:
        True if terminal likely supports ANSI colors
    """
    # Check for explicit disable via standard NO_COLOR
    if os.environ.get("NO_COLOR", ""):
        return False

    # Check for explicit disable via LKS env var
    if os.environ.get("LKS_CONSOLE_COLOR", "1") == "0":
        return False

    # Check for explicit enable (force colors even without TTY)
    if os.environ.get("FORCE_COLOR", ""):
        return True

    # Check if stdout is a TTY
    if not hasattr(sys.stdout, "isatty"):
        return False

    if not sys.stdout.isatty():
        return False

    # Windows-specific checks
    if sys.platform == "win32":
        # Windows 10+ supports ANSI via VT100 mode
        # Check for Windows Terminal, VS Code, or modern console
        if os.environ.get("WT_SESSION"):  # Windows Terminal
            return True
        if os.environ.get("TERM_PROGRAM") == "vscode":
            return True
        if os.environ.get("ANSICON"):  # ANSICON wrapper
            return True

        # Try to enable VT100 mode on Windows
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
        except Exception:
            # Fall back to no color on old Windows
            return False

    # Unix-like systems generally support colors
    return True


def get_color_enabled() -> bool:
    """
    Get whether colors are currently enabled.

    Returns:
        True if colors are enabled
    """
    global _color_enabled
    if _color_enabled is None:
        _color_enabled = supports_color()
    return _color_enabled


def set_color_enabled(enabled: bool) -> None:
    """
    Explicitly enable or disable colors.

    Args:
        enabled: Whether to enable colors
    """
    global _color_enabled
    _color_enabled = enabled


def style_text(
    text: str,
    style: LogLevel | SemanticColor | str,
    bold: bool = False,
    dim: bool = False,
    underline: bool = False,
) -> str:
    """
    Apply ANSI styling to text.

    Args:
        text: The text to style
        style: Color/style to apply (LogLevel, SemanticColor, or raw ANSI code)
        bold: Whether to make text bold
        dim: Whether to make text dim
        underline: Whether to underline text

    Returns:
        Styled text with ANSI codes, or plain text if colors disabled
    """
    if not get_color_enabled():
        return text

    # Build style prefix
    prefix: str = ""

    if bold:
        prefix += BOLD
    if dim:
        prefix += DIM
    if underline:
        prefix += UNDERLINE

    # Get color code
    if isinstance(style, (LogLevel, SemanticColor)):
        prefix += style.value
    else:
        prefix += style

    return f"{prefix}{text}{RESET}"


def strip_ansi(text: str) -> str:
    """
    Remove all ANSI escape codes from text.

    Args:
        text: Text potentially containing ANSI codes

    Returns:
        Text with all ANSI codes removed
    """
    # Pattern matches ANSI escape sequences
    ansi_pattern: str = r"\x1b\[[0-9;]*m"
    return re.sub(ansi_pattern, "", text)


def colorize_by_level(level: str) -> LogLevel:
    """
    Map a log level string to its corresponding LogLevel enum.

    Args:
        level: Log level string (debug, info, warn/warning, error)

    Returns:
        Corresponding LogLevel enum value
    """
    level_lower: str = level.lower()

    mapping: dict[str, LogLevel] = {
        "debug": LogLevel.DEBUG,
        "info": LogLevel.INFO,
        "warn": LogLevel.WARN,
        "warning": LogLevel.WARN,
        "error": LogLevel.ERROR,
        "success": LogLevel.SUCCESS,
    }

    return mapping.get(level_lower, LogLevel.INFO)


def colorize_by_duration(seconds: float, thresholds: tuple[float, float] = (1.0, 5.0)) -> SemanticColor:
    """
    Get appropriate color for a duration value.

    Args:
        seconds: Duration in seconds
        thresholds: (fast_threshold, slow_threshold) in seconds

    Returns:
        SemanticColor.FAST, MEDIUM, or SLOW based on thresholds
    """
    fast_threshold, slow_threshold = thresholds

    if seconds < fast_threshold:
        return SemanticColor.FAST
    elif seconds < slow_threshold:
        return SemanticColor.MEDIUM
    else:
        return SemanticColor.SLOW


def colorize_by_percentage(
    value: float,
    thresholds: tuple[float, float] = (50.0, 80.0),
    invert: bool = False,
) -> SemanticColor:
    """
    Get appropriate color for a percentage value.

    Args:
        value: Percentage value (0-100)
        thresholds: (low_threshold, high_threshold)
        invert: If True, high values are bad (e.g., CPU usage)

    Returns:
        Appropriate SemanticColor based on value
    """
    low_threshold, high_threshold = thresholds

    if invert:
        if value < low_threshold:
            return SemanticColor.FAST  # Green - good
        elif value < high_threshold:
            return SemanticColor.MEDIUM  # Yellow - warning
        else:
            return SemanticColor.SLOW  # Red - bad
    else:
        if value < low_threshold:
            return SemanticColor.SLOW  # Red - bad
        elif value < high_threshold:
            return SemanticColor.MEDIUM  # Yellow - okay
        else:
            return SemanticColor.FAST  # Green - good
