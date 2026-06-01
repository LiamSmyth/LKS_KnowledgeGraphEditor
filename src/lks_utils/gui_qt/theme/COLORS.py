"""
Color definitions for PySide6 GUI themes.

Semantic colors matching ttkbootstrap "darkly" theme for consistency
with existing tkinter GUIs.
"""

from __future__ import annotations

# Semantic color constants matching ttkbootstrap "darkly" theme
COLORS: dict[str, str] = {
    "bg": "#222222",
    "fg": "#ffffff",
    "primary": "#375a7f",
    "secondary": "#444444",
    "success": "#00bc8c",
    "info": "#3498db",
    "warning": "#f39c12",
    "danger": "#e74c3c",
    "light": "#adb5bd",
    "dark": "#303030",
    "border": "#444444",
    "input_bg": "#2d2d2d",
    # Button state colors
    "primary_hover": "#4a6fa5",
    "primary_pressed": "#2d4a6f",
    # Disabled colors
    "disabled_fg": "#666666",
    # Scrollbar colors
    "scrollbar_bg": "#3a3a3a",
    "scrollbar_handle": "#808080",
    "scrollbar_handle_hover": "#A0A0A0",
}

__all__ = ["COLORS"]
