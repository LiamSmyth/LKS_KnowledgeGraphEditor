"""Presentation-only display widget for string values."""

from __future__ import annotations

from lks_utils.gui_qt.components.displays.q_value_display_base import QValueDisplayBase


class QStringDisplay(QValueDisplayBase):
    """Read-only string display without field chrome."""


__all__ = ["QStringDisplay"]
