"""`RubberBandOverlay`: drag-select rectangle drawn in screen space."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE
from lks_utils.spatial.aabb import AABB


class RubberBandOverlay(ViewportOverlay):
    """Animated drag-select rectangle drawn in screen space.

    Create this overlay when a rubber-band drag begins, update
    :meth:`update_rect` on every ``mouseMoveEvent``, then remove it
    from the scene when the drag ends.

    The overlay is *screen-space* (``screen_space = True``) so the
    rect coordinates are in logical pixels relative to the widget.
    """

    screen_space = True
    accepts_input = False
    supports_gpu_rendering = False

    # Dash pattern: 4px on, 4px off.
    _DASH_ON = 4.0
    _DASH_OFF = 4.0

    def __init__(self) -> None:
        super().__init__()
        self._x0: float = 0.0
        self._y0: float = 0.0
        self._x1: float = 0.0
        self._y1: float = 0.0
        self._color_fill = QColor(PALETTE["selection_marquee"])
        self._color_fill.setAlphaF(0.10)
        self._color_pen = QColor(PALETTE["selection_marquee"])

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_start(self, screen_x: float, screen_y: float) -> None:
        """Set the anchor corner of the rubber-band rect."""
        self._x0 = screen_x
        self._y0 = screen_y
        self._x1 = screen_x
        self._y1 = screen_y
        self.request_repaint()

    def update_rect(self, screen_x: float, screen_y: float) -> None:
        """Update the live corner as the mouse moves."""
        self._x1 = screen_x
        self._y1 = screen_y
        self.request_repaint()

    def screen_rect(self) -> tuple[float, float, float, float]:
        """Return ``(x0, y0, x1, y1)`` with x0 ≤ x1, y0 ≤ y1."""
        return (
            min(self._x0, self._x1),
            min(self._y0, self._y1),
            max(self._x0, self._x1),
            max(self._y0, self._y1),
        )

    # ------------------------------------------------------------------ #
    # ViewportOverlay protocol                                             #
    # ------------------------------------------------------------------ #

    def bounds(self) -> AABB | None:
        return None  # screen-space; no meaningful world bounds

    def paint(self, ctx: CanvasPaintContext) -> None:
        x0, y0, x1, y1 = self.screen_rect()
        rect = QRectF(x0, y0, x1 - x0, y1 - y0)

        p = ctx.painter

        # Semi-transparent fill.
        p.setBrush(self._color_fill)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(rect)

        # Dashed outline (two-tone: draw white then offset black for visibility
        # on any background, like classic marching ants but static).
        pen = QPen(self._color_pen)
        pen.setCosmetic(True)
        pen.setWidthF(1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setDashPattern([self._DASH_ON, self._DASH_OFF])
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawRect(rect)

    def to_dict(self) -> dict | None:
        return None  # transient — not persisted


__all__ = ["RubberBandOverlay"]
