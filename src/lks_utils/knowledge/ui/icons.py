"""Icon loader for knowledge UI SVGs from the canonical data/icons folder."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


def get_icon(
    name: str,
    *,
    color: str | None = None,
    size_px: int = 20,
) -> QIcon | None:
    """
    Load an SVG icon from the canonical data/icons folder.

    Args:
        name: The icon name (without .svg extension).

    Returns:
        A QIcon or None if the icon cannot be loaded.
    """
    icon_path = Path(__file__).parent / "data" / "icons" / f"{name}.svg"

    if not icon_path.exists():
        return None

    try:
        if color is None:
            return QIcon(str(icon_path))

        renderer = QSvgRenderer(str(icon_path))
        if not renderer.isValid():
            return None

        pixmap = QPixmap(size_px, size_px)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        renderer.render(painter, QRectF(
            0.0, 0.0, float(size_px), float(size_px)))
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor(color))
        painter.end()

        return QIcon(pixmap)
    except Exception:
        return None


__all__ = ["get_icon"]
