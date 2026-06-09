"""Checkerboard Canvas2D overlay with zoom-invariant screen mapping."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform


class CheckerboardOverlay(ViewportOverlay):
    """Tiled checkerboard anchored to canvas position with fixed screen tile size."""

    screen_space = True
    z_order = -1000
    supports_gpu_rendering = True

    def __init__(
        self,
        *,
        tile_size_px: float = 16.0,
        scale: float = 1.0,
        opacity: float = 1.0,
        color_a: QColor | str = "#1e1f22",
        color_b: QColor | str = "#2b2d32",
    ) -> None:
        super().__init__()
        self.tile_size_px = max(float(tile_size_px), 1.0)
        self.scale = max(float(scale), 1e-6)
        self.opacity = max(0.0, min(1.0, float(opacity)))
        self._color_a = QColor(color_a) if isinstance(
            color_a, str) else QColor(color_a)
        self._color_b = QColor(color_b) if isinstance(
            color_b, str) else QColor(color_b)
        self._cpu_pixmap_cache: dict[tuple[int, int], QPixmap] = {}

    @property
    def color_a(self) -> QColor:
        return QColor(self._color_a)

    @property
    def color_b(self) -> QColor:
        return QColor(self._color_b)

    def set_colors(self, color_a: QColor | str, color_b: QColor | str) -> None:
        self._color_a = QColor(color_a) if isinstance(
            color_a, str) else QColor(color_a)
        self._color_b = QColor(color_b) if isinstance(
            color_b, str) else QColor(color_b)
        self._cpu_pixmap_cache.clear()
        self.request_repaint()

    def paint(self, ctx: CanvasPaintContext) -> None:
        pixmap = self._tiled_pixmap_for_dpr(self._device_pixel_ratio(ctx))
        p = ctx.painter
        viewport = p.viewport()
        origin_x, origin_y = self._origin_logical(
            ctx.view, ctx.viewport_size_px)

        previous_smooth = p.testRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.setOpacity(self.opacity)
        p.setBrushOrigin(origin_x, origin_y)
        p.fillRect(viewport, QBrush(pixmap))
        p.setOpacity(1.0)
        p.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform, previous_smooth)

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        renderer.render_checkerboard_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    def _tiled_pixmap_for_dpr(self, dpr: float) -> QPixmap:
        dpr_milli = max(1, int(round(dpr * 1000.0)))
        scale_milli = max(1, int(round(self.scale * 1000.0)))
        key = (dpr_milli, scale_milli)
        cached = self._cpu_pixmap_cache.get(key)
        if cached is not None:
            return cached

        tile_px = max(1, int(round(self.tile_size_px / self.scale)))
        side = max(2, tile_px * 2)
        rgba = np.empty((side, side, 4), dtype=np.uint8)

        a = self._color_rgba8(self._color_a)
        b = self._color_rgba8(self._color_b)

        rgba[:, :, :] = 0
        rgba[:tile_px, :tile_px] = a
        rgba[:tile_px, tile_px:] = b
        rgba[tile_px:, :tile_px] = b
        rgba[tile_px:, tile_px:] = a

        qimg = QImage(
            rgba.data,
            side,
            side,
            side * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        pixmap = QPixmap.fromImage(qimg)
        pixmap.setDevicePixelRatio(dpr)
        self._cpu_pixmap_cache[key] = pixmap
        return pixmap

    @staticmethod
    def _color_rgba8(color: QColor) -> np.ndarray:
        return np.array(
            [color.red(), color.green(), color.blue(), color.alpha()],
            dtype=np.uint8,
        )

    @staticmethod
    def _origin_logical(
        view: ViewTransform,
        viewport_size_px: tuple[float, float],
    ) -> tuple[float, float]:
        half_w = viewport_size_px[0] * 0.5
        half_h = viewport_size_px[1] * 0.5
        x = half_w - float(view.center_world[0]) * float(view.zoom)
        y = half_h + float(view.center_world[1]) * float(view.zoom)
        return (x, y)

    @staticmethod
    def _device_pixel_ratio(ctx: CanvasPaintContext) -> float:
        dpr = max(ctx.device_pixel_ratio, 1.0)
        device = ctx.painter.device()
        getter = getattr(device, "devicePixelRatioF", None)
        if callable(getter):
            dpr = max(dpr, float(getter()))
        return dpr


__all__ = ["CheckerboardOverlay"]
