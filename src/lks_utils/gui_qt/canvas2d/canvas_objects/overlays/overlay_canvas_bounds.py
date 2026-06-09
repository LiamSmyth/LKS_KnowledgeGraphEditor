"""Tool 1 — Canvas2D object-bounds debug overlay.

Draws a 1px red AABB per scene object in screen space, with an optional
class-name label at the top-left corner.  Off by default; activated via
:meth:`~lks_utils.gui_qt.canvas2d.widgets.canvas_widget.Canvas2DWidget.enable_debug_bounds`
or the ``LKS_DEBUG_CANVAS_BOUNDS=1`` environment variable.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPen

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D


class CanvasBoundsOverlay(ViewportOverlay):
    """Draws each scene object's world-space :meth:`~CanvasObject.bounds` AABB
    as a 1px red rectangle in screen space.

    The overlay holds a reference to :class:`~lks_utils.gui_qt.canvas2d.core.scene2d.Scene2D`
    so it can iterate items at paint time.

    Activation
    ----------
    * Call ``Canvas2DWidget.enable_debug_bounds(show_labels=True)``
    * Or set ``LKS_DEBUG_CANVAS_BOUNDS=1`` before import.
    """

    screen_space: bool = False
    accepts_input: bool = False
    supports_gpu_rendering: bool = False
    z_order: int = 9000  # paint on top of everything

    def __init__(self, scene: Scene2D, *, show_labels: bool = True) -> None:
        super().__init__()
        self._scene = scene
        self.show_labels: bool = show_labels
        self._pen = QPen(QColor(PALETTE["canvas2d_debug_bounds_stroke"]))
        self._pen.setCosmetic(True)
        self._pen.setWidthF(1.0)
        self._label_color = QColor(PALETTE["canvas2d_debug_bounds_label"])
        self._label_font = QFont("Courier New")
        self._label_font.setPixelSize(10)

    def paint(self, ctx: CanvasPaintContext) -> None:
        """Paint AABB rectangles for every scene object."""
        painter = ctx.painter
        view = ctx.view
        vp_size = ctx.viewport_size_px

        # Save painter state — we'll draw in screen space.
        painter.save()
        painter.resetTransform()

        painter.setPen(self._pen)
        if self.show_labels:
            painter.setFont(self._label_font)

        for obj in self._scene.objects():
            bounds: AABB | None = obj.bounds()
            if bounds is None:
                continue

            # Project all four corners to screen space.
            sx0, sy0 = view.world_to_screen(
                (bounds.x0, bounds.y0), vp_size
            )
            sx1, sy1 = view.world_to_screen(
                (bounds.x1, bounds.y1), vp_size
            )

            # Build a normalised QRectF (handles flipped coords).
            rect = QRectF(
                QPointF(min(sx0, sx1), min(sy0, sy1)),
                QPointF(max(sx0, sx1), max(sy0, sy1)),
            )
            painter.drawRect(rect)

            if self.show_labels:
                label = type(obj).__name__
                painter.setPen(QPen(self._label_color))
                painter.drawText(
                    QPointF(rect.left() + 2.0, rect.top() + 10.0), label
                )
                painter.setPen(self._pen)

        painter.restore()

    def bounds(self) -> AABB | None:
        """Unbounded — always rendered."""
        return None


def maybe_auto_install(canvas: object) -> None:
    """Install a :class:`CanvasBoundsOverlay` if ``LKS_DEBUG_CANVAS_BOUNDS=1``."""
    if os.environ.get("LKS_DEBUG_CANVAS_BOUNDS") == "1":
        canvas.add_overlay(CanvasBoundsOverlay())  # type: ignore[union-attr]


__all__ = ["CanvasBoundsOverlay", "maybe_auto_install"]
