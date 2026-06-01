"""Presentation-only display widgets for bool/bytes/none/color/vector values."""

from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.components.displays.q_value_display_base import QValueDisplayBase, format_display_value


class QBoolDisplay(QValueDisplayBase):
    """Read-only bool display without field chrome."""


class QBytesDisplay(QValueDisplayBase):
    """Read-only bytes display without field chrome."""


class QNoneDisplay(QValueDisplayBase):
    """Read-only none display without field chrome."""


class QColorDisplay(QValueDisplayBase):
    """Read-only color display without field chrome."""


class QVectorDisplay(QValueDisplayBase):
    """Read-only vector display without field chrome."""

    def format_value(self, value: Any) -> str:
        return format_display_value(value)


__all__ = [
    "QBoolDisplay",
    "QBytesDisplay",
    "QNoneDisplay",
    "QColorDisplay",
    "QVectorDisplay",
]
