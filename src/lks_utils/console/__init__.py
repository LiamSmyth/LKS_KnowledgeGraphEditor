"""
Console utilities for beautiful, colorized terminal output.

This module provides ANSI color support, table formatting, and styled output
for console applications. It gracefully degrades to plain text when colors
are not supported or when the optional `rich` dependency is not installed.

Optional Dependencies:
    Install with: pip install lks-utils[console]
    - rich>=13.0.0: Full-featured console formatting

Environment Variables:
    LKS_CONSOLE_COLOR: Set to "0" to disable colors globally
    NO_COLOR: Standard env var to disable colors (https://no-color.org/)

Usage:
    from lks_utils.console import style, LogLevel, print_styled
    
    # Simple styled output
    print_styled("Success!", style=LogLevel.SUCCESS)
    print_styled("Warning!", style=LogLevel.WARN)
    
    # Check color support
    from lks_utils.console import supports_color
    if supports_color():
        print("Terminal supports colors")
"""

from __future__ import annotations

from lks_utils.console.colors import RESET, LogLevel, SemanticColor, style_text, strip_ansi, supports_color, get_color_enabled, set_color_enabled

from lks_utils.console.formatters import Table, Panel, format_duration, format_percentage, format_size, create_progress_bar

__all__ = [
    # Colors
    "RESET",
    "LogLevel",
    "SemanticColor",
    "style_text",
    "strip_ansi",
    "supports_color",
    "get_color_enabled",
    "set_color_enabled",
    # Formatters
    "Table",
    "Panel",
    "format_duration",
    "format_percentage",
    "format_size",
    "create_progress_bar",
]
