"""Dock drop-region hit-testing helpers."""
from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QPolygon


class DockDropRegion(str, Enum):
    """Edge regions used for split docking previews."""

    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


def diagonal_region(rect: QRect, local_pos: QPoint) -> DockDropRegion | None:
    """Divide the rect into four non-overlapping triangular regions using both diagonals.

    The rect is split by both corner-to-corner diagonals, creating four
    trapezoid-shaped regions (triangles meeting at the center).  Every pixel
    inside the rect maps to exactly one region — no dead zones, no overlaps.

    Corner pixels that land exactly on a diagonal line fall through to LEFT.
    """
    if rect.width() <= 0 or rect.height() <= 0:
        return None

    px = local_pos.x() - rect.left()
    py = local_pos.y() - rect.top()
    w = rect.width()
    h = rect.height()

    if px < 0 or py < 0 or px >= w or py >= h:
        return None

    # Normalize to [0, w*h] scale to avoid float division.
    # Diagonals: y/h = x/w  =>  y*w = x*h   (main diagonal)
    #            y/h = 1 - x/w  =>  y*w + x*h = w*h  (anti-diagonal)
    yw = py * w
    xh = px * h
    wh = w * h

    if yw < xh and yw + xh < wh:     # above both diagonals
        return DockDropRegion.TOP
    if yw < xh and yw + xh >= wh:    # above main, below anti
        return DockDropRegion.RIGHT
    if yw >= xh and yw + xh >= wh:   # below both diagonals
        return DockDropRegion.BOTTOM
    return DockDropRegion.LEFT       # below main, above anti


def region_diagonal_polygon(rect: QRect, region: DockDropRegion) -> QPolygon:
    """Return the triangular QPolygon for a diagonal region, used for debug overlay drawing."""
    tl = rect.topLeft()
    tr = rect.topRight()
    bl = rect.bottomLeft()
    br = rect.bottomRight()
    cx = rect.center().x()
    cy = rect.center().y()
    center = QPoint(cx, cy)

    if region == DockDropRegion.TOP:
        return QPolygon([tl, tr, center])
    if region == DockDropRegion.RIGHT:
        return QPolygon([tr, br, center])
    if region == DockDropRegion.BOTTOM:
        return QPolygon([br, bl, center])
    return QPolygon([bl, tl, center])


def resolve_drop_region(
    rect: QRect,
    local_pos: QPoint,
    edge_fraction: float = 0.25,   # kept for API compat, unused
    min_band_px: int = 24,          # kept for API compat, unused
    allow_center_snap: bool = False,  # kept for API compat, unused
) -> DockDropRegion | None:
    """Return the drop region for *local_pos* inside *rect*.

    Delegates to :func:`diagonal_region` which guarantees full coverage with
    zero overlap.  Parameters ``edge_fraction``, ``min_band_px``, and
    ``allow_center_snap`` are retained for backwards compatibility but
    have no effect.
    """
    return diagonal_region(rect, local_pos)


# ---------------------------------------------------------------------------
# Preview rectangle helpers (rectangular bands used for drop-preview UI)
# ---------------------------------------------------------------------------

def region_rect(rect: QRect, region: DockDropRegion, edge_fraction: float = 0.33) -> QRect:
    """Compute the preview rectangle for a resolved drop region."""
    w = max(1, int(rect.width() * edge_fraction))
    h = max(1, int(rect.height() * edge_fraction))

    if region == DockDropRegion.TOP:
        return QRect(rect.left(), rect.top(), rect.width(), h)
    if region == DockDropRegion.BOTTOM:
        return QRect(rect.left(), rect.bottom() - h + 1, rect.width(), h)
    if region == DockDropRegion.LEFT:
        return QRect(rect.left(), rect.top(), w, rect.height())
    return QRect(rect.right() - w + 1, rect.top(), w, rect.height())
