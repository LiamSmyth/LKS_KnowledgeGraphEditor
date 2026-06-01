"""Spacing constants for PySide6 GUIs.

Named pixel constants for paddings, gaps, and row heights. Per
Phase 17h, all UI widgets should consume these instead of bare pixel
literals so a future "compact" / "spacious" mode is a single-file
change.
"""
from __future__ import annotations


# Padding (inside a widget, around its contents).
PAD_XS: int = 2
PAD_SM: int = 4
PAD_MD: int = 8
PAD_LG: int = 12
PAD_XL: int = 16

# Gap (between sibling widgets in a layout).
GAP_XS: int = 2
GAP_SM: int = 4
GAP_MD: int = 8
GAP_LG: int = 12

# Row heights (lists, tables, layer panel rows, etc.).
ROW_HEIGHT_COMPACT: int = 24
ROW_HEIGHT_DEFAULT: int = 32
ROW_HEIGHT_RELAXED: int = 40

# Border radii.
RADIUS_SM: int = 2
RADIUS_MD: int = 4
RADIUS_LG: int = 8

# Border widths.
BORDER_THIN: int = 1
BORDER_MEDIUM: int = 2

# Standard icon / thumbnail sizes.
ICON_XS: int = 12
ICON_SM: int = 16
ICON_MD: int = 24
ICON_LG: int = 32
THUMBNAIL_LAYER_ROW: int = 24


__all__ = [
    "PAD_XS", "PAD_SM", "PAD_MD", "PAD_LG", "PAD_XL",
    "GAP_XS", "GAP_SM", "GAP_MD", "GAP_LG",
    "ROW_HEIGHT_COMPACT", "ROW_HEIGHT_DEFAULT", "ROW_HEIGHT_RELAXED",
    "RADIUS_SM", "RADIUS_MD", "RADIUS_LG",
    "BORDER_THIN", "BORDER_MEDIUM",
    "ICON_XS", "ICON_SM", "ICON_MD", "ICON_LG",
    "THUMBNAIL_LAYER_ROW",
]
