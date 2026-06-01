"""
Lightweight logging helpers for lks_utils with optional color support.

Goals
- Keep verbose logging out of core logic by centralizing print calls here.
- Provide timing helpers for quick duration instrumentation.
- Respect LKS_VERBOSE_LOGGING environment variable for debug noise control.
- Support colorized output when lks_utils.console is available.

Usage
    from lks_utils import log_info, log_debug, log_warn, log_error, timed, timeit

    log_info("ImageSaver", f"Saved {n} files to {out}")

    with timed("BatchProcessor", "resize"):
        resize_images(...)

    @timeit("Gatherer")
    def gather(...):
        ...

Configuration (environment variables):
    LKS_VERBOSE_LOGGING: "1" to enable debug logs (default: "0")
    LKS_PATCH_PRINT: "0" to disable global print normalization (default: "1")
    LKS_CONSOLE_COLOR: "0" to disable colors (default: "1" / auto-detect)
"""

from __future__ import annotations
from ..text.normalization import normalize_text_for_console as _norm

import builtins
import os
import time
from typing import Callable
import sys

# Read config from environment (no external config.py dependency)
VERBOSE_LOGGING = os.environ.get("LKS_VERBOSE_LOGGING", "0") == "1"

# Try to import console colors (optional dependency)
try:
    from ..console.colors import (
        LogLevel,
        SemanticColor,
        style_text,
        get_color_enabled,
    )
    from ..console.formatters import format_duration
    HAS_CONSOLE: bool = True
except ImportError:
    HAS_CONSOLE = False

    # Fallback stubs
    def style_text(text: str, style, **kwargs) -> str:  # type: ignore
        return text

    def get_color_enabled() -> bool:
        return False

    def format_duration(seconds: float, **kwargs) -> str:  # type: ignore
        return f"{seconds * 1000:.1f}ms"

def safe_print(*parts, sep: str = " ", end: str = "\n") -> None:
    """Print with mojibake/emoji normalization."""
    try:
        text = sep.join(_norm(str(p)) for p in parts)
        print(text, end=end)
    except Exception:
        # Last-resort raw print
        print(*parts, sep=sep, end=end)

def _prefix(component: str | None, colorize: bool = True) -> str:
    """Generate the LKS/ prefix with optional coloring."""
    prefix: str = f"LKS/{component}: " if component else "LKS: "
    if colorize and HAS_CONSOLE and get_color_enabled():
        return style_text(prefix, SemanticColor.MUTED)
    return prefix

def log_info(component: str | None, message: str, *, color: bool = True) -> None:
    """
    Log an info message.

    Args:
        component: Component name for prefix (e.g., "ImageSaver")
        message: The message to log
        color: Whether to colorize output (default True)
    """
    prefix: str = _prefix(component, colorize=color)
    safe_print(f"{prefix}{message}")

def log_warn(component: str | None, message: str, *, color: bool = True) -> None:
    """
    Log a warning message with yellow styling.

    Args:
        component: Component name for prefix
        message: The warning message
        color: Whether to colorize output (default True)
    """
    prefix: str = _prefix(component, colorize=color)
    indicator: str = "⚠️ "
    styled_message: str = message
    if color and HAS_CONSOLE and get_color_enabled():
        styled_message = style_text(message, LogLevel.WARN)
    safe_print(f"{prefix}{indicator}{styled_message}")

def log_error(component: str | None, message: str, *, color: bool = True) -> None:
    """
    Log an error message with red styling.

    Args:
        component: Component name for prefix
        message: The error message
        color: Whether to colorize output (default True)
    """
    prefix: str = _prefix(component, colorize=color)
    indicator: str = "❌ "
    styled_message: str = message
    if color and HAS_CONSOLE and get_color_enabled():
        styled_message = style_text(message, LogLevel.ERROR)
    safe_print(f"{prefix}{indicator}{styled_message}")

def log_success(component: str | None, message: str, *, color: bool = True) -> None:
    """
    Log a success message with green styling.

    Args:
        component: Component name for prefix
        message: The success message
        color: Whether to colorize output (default True)
    """
    prefix: str = _prefix(component, colorize=color)
    indicator: str = "✓ "
    styled_message: str = message
    if color and HAS_CONSOLE and get_color_enabled():
        indicator = style_text("✓ ", LogLevel.SUCCESS)
        styled_message = style_text(message, LogLevel.SUCCESS)
    safe_print(f"{prefix}{indicator}{styled_message}")

def log_debug(component: str | None, message: str, *, color: bool = True) -> None:
    """
    Log a debug message (only if LKS_VERBOSE_LOGGING=1).

    Args:
        component: Component name for prefix
        message: The debug message
        color: Whether to colorize output (default True)
    """
    if VERBOSE_LOGGING:
        prefix: str = _prefix(component, colorize=color)
        label: str = "[debug] "
        styled_message: str = message
        if color and HAS_CONSOLE and get_color_enabled():
            label = style_text("[debug] ", LogLevel.DEBUG)
            styled_message = style_text(message, LogLevel.DEBUG)
        safe_print(f"{prefix}{label}{styled_message}")

# --- Global print normalizer (mojibake/emojis) ---
if os.environ.get("LKS_PATCH_PRINT", "1") == "1":
    try:
        # Avoid double-wrapping and recursion if module is reloaded
        if not getattr(builtins.print, "_lks_normalized", False):
            _ORIGINAL_PRINT = builtins.print

            def _normalized_print(*args, sep: str = " ", end: str = "\n", file=None, flush: bool = False):
                try:
                    norm_args = [
                        _norm(a if isinstance(a, str) else str(a))
                        for a in args
                    ]
                    _ORIGINAL_PRINT(*norm_args, sep=sep,
                                    end=end, file=file, flush=flush)
                except UnicodeEncodeError:
                    # If encoding fails, try to encode with replacement
                    target_file = file or sys.stdout
                    encoding = getattr(
                        target_file, "encoding", "utf-8") or "utf-8"

                    safe_args = []
                    for a in args:
                        s = a if isinstance(a, str) else str(a)
                        # Encode and decode with 'replace' to remove unencodable chars
                        safe_args.append(
                            s.encode(encoding, errors="replace").decode(encoding))

                    _ORIGINAL_PRINT(*safe_args, sep=sep,
                                    end=end, file=file, flush=flush)
                except Exception:
                    # Fallback to original for other errors
                    _ORIGINAL_PRINT(*args, sep=sep, end=end,
                                    file=file, flush=flush)

            # type: ignore[attr-defined]
            _normalized_print._lks_normalized = True
            builtins.print = _normalized_print  # type: ignore[assignment]
    except Exception:
        # If patching fails, continue without global patch
        pass

class timed:
    """
    Context manager for timing a block and logging duration with color.

    Usage:
        with timed("ImageProcessor", "resize"):
            resize_images(...)

    Output:
        LKS/ImageProcessor: resize done in 1.23s
    """

    def __init__(self, component: str | None, label: str, color: bool = True):
        self.component = component
        self.label = label
        self.color = color
        self._start: float = 0.0
        self.duration_seconds: float = 0.0

    def __enter__(self) -> "timed":
        self._start = time.time()
        log_debug(self.component, f"start: {self.label}", color=self.color)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.duration_seconds = time.time() - self._start
        dur_str: str = format_duration(
            self.duration_seconds, colorize=self.color)

        if exc is None:
            log_info(self.component,
                     f"{self.label} done in {dur_str}", color=self.color)
        else:
            log_error(
                self.component,
                f"{self.label} failed after {dur_str}: {exc}",
                color=self.color,
            )
        # Do not suppress exceptions
        return False

def timeit(component: str | None, label: str | None = None, color: bool = True) -> Callable:
    """
    Decorator to time a function call and log duration with color.

    Args:
        component: Component name for log prefix
        label: Custom label (defaults to function name)
        color: Whether to colorize output

    Usage:
        @timeit("Gatherer")
        def gather_files():
            ...
    """

    def deco(fn: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            name: str = label or fn.__name__
            start: float = time.time()
            log_debug(component, f"start: {name}", color=color)
            try:
                return fn(*args, **kwargs)
            finally:
                dur_seconds: float = time.time() - start
                dur_str: str = format_duration(dur_seconds, colorize=color)
                log_info(component, f"{name} done in {dur_str}", color=color)

        return wrapper

    return deco
