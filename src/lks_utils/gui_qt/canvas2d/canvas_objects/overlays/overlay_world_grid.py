"""`WorldGridOverlay`: infinite world-space line grid with LOD carousel.

The grid is anchored in world coordinates and rendered with two adjacent
zoom levels that cross-fade smoothly. This keeps every zoom octave
isomorphic while avoiding abrupt pops at level boundaries.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QLineF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform


class WorldGridOverlay(ViewportOverlay):
    """World-space line grid with smooth octave cross-fade.

    Args:
        grid_scale: Base world step size at 1x zoom.
        line_width_px: Major-line width in screen pixels.
        minor_alpha: Opacity multiplier for the finer level.
        minor_line_width_px: Finer-level width in screen pixels.
        lod_base: Ratio between adjacent levels (default 2.0).
        max_lines_per_axis: Safety cap for one level in one axis.
    """

    screen_space = False
    z_order = -1000
    supports_gpu_rendering = True

    def __init__(
        self,
        grid_scale: float = 64.0,
        line_width_px: float = 1.25,
        minor_alpha: float = 0.35,
        minor_line_width_px: float = 1.0,
        lod_base: float = 2.0,
        max_lines_per_axis: int = 4000,
    ) -> None:
        super().__init__()
        self.grid_scale = max(float(grid_scale), 1e-9)
        self.line_width_px = max(float(line_width_px), 0.25)
        self.minor_alpha = max(0.0, min(1.0, float(minor_alpha)))
        self.minor_line_width_px = max(float(minor_line_width_px), 0.25)
        self.lod_base = max(float(lod_base), 1.0001)
        self.max_lines_per_axis = max(16, int(max_lines_per_axis))
        self._minor_color = QColor(PALETTE["dot_grid"])
        self._major_color = QColor(PALETTE["dot_grid_strong"])

    @staticmethod
    def _smoothstep01(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def _with_alpha(color: QColor, alpha_01: float) -> QColor:
        tint = QColor(color)
        tint.setAlpha(int(round(max(0.0, min(1.0, alpha_01)) * 255.0)))
        return tint

    def _lod_pair_for_zoom(self, zoom: float) -> tuple[float, float, float, float]:
        """Return coarse/fine steps and corresponding blend weights.

        Returns:
            (coarse_step, fine_step, coarse_alpha, fine_alpha)
        """
        log_zoom = math.log(max(zoom, 1e-9), self.lod_base)
        level = math.floor(log_zoom)
        blend = self._smoothstep01(log_zoom - level)
        coarse_step = self.grid_scale / (self.lod_base**level)
        fine_step = coarse_step / self.lod_base
        return coarse_step, fine_step, 1.0 - blend, blend

    @staticmethod
    def _line_index_bounds(x0: float, x1: float, step: float) -> tuple[int, int]:
        return int(math.floor(x0 / step)) - 1, int(math.ceil(x1 / step)) + 1

    def _make_pen(self, color: QColor, width_px: float) -> QPen:
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidthF(width_px)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        return pen

    def _draw_level(
        self,
        ctx: CanvasPaintContext,
        *,
        step: float,
        alpha: float,
        width_px: float,
        color: QColor,
    ) -> None:
        if alpha <= 0.01 or step <= 0.0:
            return

        aabb = ctx.viewport_aabb_world
        i_min, i_max = self._line_index_bounds(aabb.x0, aabb.x1, step)
        j_min, j_max = self._line_index_bounds(aabb.y0, aabb.y1, step)
        n_x = i_max - i_min + 1
        n_y = j_max - j_min + 1
        if n_x > self.max_lines_per_axis or n_y > self.max_lines_per_axis:
            return

        y0 = float(aabb.y0 - step)
        y1 = float(aabb.y1 + step)
        x0 = float(aabb.x0 - step)
        x1 = float(aabb.x1 + step)

        v_lines = [
            QLineF(float(i * step), y0, float(i * step), y1)
            for i in range(i_min, i_max + 1)
        ]
        h_lines = [
            QLineF(x0, float(j * step), x1, float(j * step))
            for j in range(j_min, j_max + 1)
        ]

        p = ctx.painter
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(self._make_pen(self._with_alpha(color, alpha), width_px))
        p.drawLines(v_lines)
        p.drawLines(h_lines)

    def paint(self, ctx: CanvasPaintContext) -> None:
        coarse_step, fine_step, coarse_alpha, fine_alpha = self._lod_pair_for_zoom(
            max(ctx.view.zoom, 1e-9)
        )
        self._draw_level(
            ctx,
            step=fine_step,
            alpha=fine_alpha * self.minor_alpha,
            width_px=self.minor_line_width_px,
            color=self._minor_color,
        )
        self._draw_level(
            ctx,
            step=coarse_step,
            alpha=coarse_alpha,
            width_px=self.line_width_px,
            color=self._major_color,
        )

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        renderer.render_world_grid_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    def to_dict(self) -> dict:
        return {
            "type": "canvas2d.overlays.world_grid",
            "grid_scale": self.grid_scale,
            "line_width_px": self.line_width_px,
            "minor_alpha": self.minor_alpha,
            "minor_line_width_px": self.minor_line_width_px,
            "lod_base": self.lod_base,
            "max_lines_per_axis": self.max_lines_per_axis,
        }

    @classmethod
    def from_dict(cls, d: dict) -> WorldGridOverlay:
        grid_scale = float(d.get("grid_scale", d.get("world_spacing", 64.0)))
        return cls(
            grid_scale=grid_scale,
            line_width_px=float(d.get("line_width_px", 1.25)),
            minor_alpha=float(d.get("minor_alpha", 0.35)),
            minor_line_width_px=float(d.get("minor_line_width_px", 1.0)),
            lod_base=float(d.get("lod_base", 2.0)),
            max_lines_per_axis=int(d.get("max_lines_per_axis", 4000)),
        )


__all__ = ["WorldGridOverlay"]
