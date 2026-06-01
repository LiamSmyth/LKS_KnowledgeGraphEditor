"""Infinite origin axes overlay for Canvas2D."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen

from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform


class AxesLinesOverlay(ViewportOverlay):
    """Infinite X/Y axis lines anchored at world origin.

    The horizontal axis is fixed red by request; vertical axis keeps the
    existing semantic palette color.
    """

    screen_space = False
    z_order = -490
    supports_gpu_rendering = True

    def __init__(self) -> None:
        super().__init__()
        # Keep X axis hard-red regardless of theme overrides.
        self._x_color = QColor(PALETTE["canvas2d_grid_axis_x"])
        self._y_color = QColor(PALETTE["canvas2d_grid_axis_y"])
        self._line_width_px = 1.6

    def paint(self, ctx: CanvasPaintContext) -> None:
        aabb = ctx.viewport_aabb_world
        p = ctx.painter

        x_pen = QPen(self._x_color)
        x_pen.setCosmetic(True)
        x_pen.setWidthF(self._line_width_px)
        x_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(x_pen)
        p.drawLine(QPointF(aabb.x0, 0.0), QPointF(aabb.x1, 0.0))

        y_pen = QPen(self._y_color)
        y_pen.setCosmetic(True)
        y_pen.setWidthF(self._line_width_px)
        y_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(y_pen)
        p.drawLine(QPointF(0.0, aabb.y0), QPointF(0.0, aabb.y1))

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        renderer.render_axes_lines_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    @property
    def x_color(self) -> QColor:
        return QColor(self._x_color)

    @property
    def y_color(self) -> QColor:
        return QColor(self._y_color)

    @property
    def line_width_px(self) -> float:
        return float(self._line_width_px)

    def to_dict(self) -> dict:
        return {"type": "canvas2d.overlays.axes_lines"}

    @classmethod
    def from_dict(cls, d: dict) -> AxesLinesOverlay:
        del d
        return cls()


__all__ = ["AxesLinesOverlay"]
