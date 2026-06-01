"""Presentation-only display widgets for numeric values."""

from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.components.displays.q_value_display_base import QValueDisplayBase


class QIntDisplay(QValueDisplayBase):
    """Read-only integer display without field chrome."""


class QFloatDisplay(QValueDisplayBase):
    """Read-only float display without field chrome."""

    def format_value(self, value: Any) -> str:
        if value is None:
            return "None"
        return f"{float(value):.6g}"


__all__ = ["QIntDisplay", "QFloatDisplay"]
