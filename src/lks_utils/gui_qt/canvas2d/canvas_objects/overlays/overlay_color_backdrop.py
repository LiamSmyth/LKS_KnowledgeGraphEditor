"""Solid-colour backdrop overlay for Canvas2D.

A ``ViewportOverlay`` with ``z_order=-1000`` and ``screen_space=True``
that fills the viewport with a flat colour before any items are painted.

Usage::

    from PySide6.QtGui import QColor
    canvas.add_overlay(ColorBackdrop(QColor(PALETTE["panel_bg"])))

The backdrop renders underneath all canvas objects because its z_order is
deeply negative.  Use a negative-z_order ``ViewportOverlay`` whenever
you need a custom background other than the default dark panel colour.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QColor, QPainter

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform


class ColorBackdrop(ViewportOverlay):
    """Fill the entire viewport with a solid colour.

    Parameters
    ----------
    color:
        Background colour to paint.  Any ``QColor``-compatible value.
    """

    z_order: int = -1000
    screen_space: bool = True
    supports_gpu_rendering: bool = True

    def __init__(self, color: QColor | str) -> None:
        super().__init__()
        self._color: QColor = QColor(
            color) if isinstance(color, str) else color

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @property
    def color(self) -> QColor:
        """The current backdrop colour."""
        return self._color

    def set_color(self, color: QColor | str) -> None:
        """Change the backdrop colour and request a repaint."""
        self._color = QColor(color) if isinstance(color, str) else color
        self.request_repaint()

    # ------------------------------------------------------------------ #
    # CanvasObject interface                                                 #
    # ------------------------------------------------------------------ #

    def paint(self, ctx: CanvasPaintContext) -> None:
        """Fill the viewport rect with the backdrop colour."""
        ctx.painter.fillRect(ctx.painter.viewport(), self._color)

    def bounds(self):  # noqa: ANN201
        """Backdrop has no logical bounds — return ``None``."""
        return None

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        del view, viewport_px, viewport_logical_px, device_pixel_ratio
        renderer.render_color_backdrop_overlay(self)


__all__ = ["ColorBackdrop"]
