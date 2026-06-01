"""Helpers to build presentation-only display widgets from type names."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QWidget

from lks_utils.gui_qt.components.displays.q_misc_displays import (
    QBoolDisplay,
    QBytesDisplay,
    QColorDisplay,
    QNoneDisplay,
    QVectorDisplay,
)
from lks_utils.gui_qt.components.displays.q_number_display import QFloatDisplay, QIntDisplay
from lks_utils.gui_qt.components.displays.q_string_display import QStringDisplay

SUPPORTED_DISPLAY_TYPES: tuple[str, ...] = (
    "string",
    "int",
    "float",
    "bool",
    "bytes",
    "none",
    "color",
    "vector2",
    "vector3",
    "vector4",
)


def make_display_for_type(type_name: str, *, value: Any = None, parent: QWidget | None = None) -> QWidget:
    """Build a read-only display widget for a primitive type name."""
    key = type_name.strip().lower()

    if key == "int":
        return QIntDisplay(value, parent=parent)
    if key == "float":
        return QFloatDisplay(value, parent=parent)
    if key == "bool":
        return QBoolDisplay(value, parent=parent)
    if key == "bytes":
        return QBytesDisplay(value, parent=parent)
    if key == "none":
        return QNoneDisplay(value, parent=parent)
    if key == "color":
        return QColorDisplay(value, parent=parent)
    if key in {"vector2", "vector3", "vector4"}:
        return QVectorDisplay(value, parent=parent)
    return QStringDisplay(value, parent=parent)


__all__ = ["SUPPORTED_DISPLAY_TYPES", "make_display_for_type"]
