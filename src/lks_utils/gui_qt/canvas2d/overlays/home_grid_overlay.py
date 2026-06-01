"""Finite home grid overlay anchored at world origin."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen

from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform


class HomeGridOverlay(ViewportOverlay):
    """Origin-centered finite grid with border, no zoom carousel."""

    screen_space = False
    z_order = -500
    supports_gpu_rendering = True

    # One demo "canvas unit" in world coordinates (matches existing demo scale).
    UNIT_WORLD = 100.0

    def __init__(
        self,
        extent: float = 8.0,
        subdivisions: int = 1,
        line_thickness_px: float = 1.0,
        border_thickness_px: float = 1.6,
        color: QColor | str = "#60b0b0b0",
        border_color: QColor | str = "#c0d0d0d0",
    ) -> None:
        super().__init__()
        self.extent = max(float(extent), 0.0)
        self.subdivisions = max(1, int(subdivisions))
        self.line_thickness_px = max(float(line_thickness_px), 0.25)
        self.border_thickness_px = max(float(border_thickness_px), 0.25)
        self._color = QColor(color) if isinstance(color, str) else QColor(color)
        self._border_color = (
            QColor(border_color) if isinstance(border_color, str) else QColor(border_color)
        )

    @property
    def extent_world(self) -> float:
        return self.extent * self.UNIT_WORLD

    @property
    def step_world(self) -> float:
        return self.UNIT_WORLD / float(max(1, self.subdivisions))

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    @property
    def border_color(self) -> QColor:
        return QColor(self._border_color)

    def bounds(self) -> AABB:
        e = self.extent_world
        return AABB(-e, -e, e, e)

    @staticmethod
    def _line_index_bounds(x0: float, x1: float, step: float) -> tuple[int, int]:
        return int(math.floor(x0 / step)) - 1, int(math.ceil(x1 / step)) + 1

    def paint(self, ctx: CanvasPaintContext) -> None:
        e = self.extent_world
        if e <= 0.0:
            return
        step = self.step_world
        p = ctx.painter

        line_pen = QPen(self._color)
        line_pen.setCosmetic(True)
        line_pen.setWidthF(self.line_thickness_px)
        line_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(line_pen)

        imin, imax = self._line_index_bounds(-e, e, step)
        v_lines: list[QLineF] = []
        h_lines: list[QLineF] = []
        for i in range(imin, imax + 1):
            x = float(i * step)
            if x < -e - 1e-9 or x > e + 1e-9:
                continue
            v_lines.append(QLineF(x, -e, x, e))
            h_lines.append(QLineF(-e, x, e, x))
        if v_lines:
            p.drawLines(v_lines)
            p.drawLines(h_lines)

        border_pen = QPen(self._border_color)
        border_pen.setCosmetic(True)
        border_pen.setWidthF(self.border_thickness_px)
        border_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(QPointF(-e, -e), QPointF(e, e)))

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        renderer.render_home_grid_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    def to_dict(self) -> dict:
        return {
            "type": "canvas2d.overlays.home_grid",
            "extent": self.extent,
            "subdivisions": self.subdivisions,
            "line_thickness_px": self.line_thickness_px,
            "border_thickness_px": self.border_thickness_px,
            "color": self._color.name(QColor.NameFormat.HexArgb),
            "border_color": self._border_color.name(QColor.NameFormat.HexArgb),
        }

    @classmethod
    def from_dict(cls, d: dict) -> HomeGridOverlay:
        return cls(
            extent=float(d.get("extent", 8.0)),
            subdivisions=int(d.get("subdivisions", 1)),
            line_thickness_px=float(d.get("line_thickness_px", 1.0)),
            border_thickness_px=float(d.get("border_thickness_px", 1.6)),
            color=str(d.get("color", "#60b0b0b0")),
            border_color=str(d.get("border_color", "#c0d0d0d0")),
        )


__all__ = ["HomeGridOverlay"]
