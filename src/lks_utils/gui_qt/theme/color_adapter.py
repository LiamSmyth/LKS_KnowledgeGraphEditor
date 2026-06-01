"""Bidirectional adapter between lks_utils Color and PySide6 QColor."""
from __future__ import annotations

from lks_utils.theme.color import Color

from PySide6.QtGui import QColor


def to_qcolor(color: Color) -> QColor:
    """Convert a :class:`~lks_utils.theme.Color` to a :class:`QColor`."""
    return QColor(color.r, color.g, color.b, color.a)


def from_qcolor(qcolor: QColor) -> Color:
    """Convert a :class:`QColor` to a :class:`~lks_utils.theme.Color`."""
    return Color(
        r=qcolor.red(),
        g=qcolor.green(),
        b=qcolor.blue(),
        a=qcolor.alpha(),
    )


__all__ = ["to_qcolor", "from_qcolor"]
