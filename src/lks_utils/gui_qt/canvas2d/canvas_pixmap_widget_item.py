"""Pixmap-backed CanvasItem adapter for canvas-blind Qt widgets."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from lks_utils.gui_qt.canvas2d.canvas_item_registry import register_canvas_item_type
from lks_utils.gui_qt.canvas2d.canvas_widget_adapter_base import CanvasWidgetAdapterBase

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext


class _WidgetUpdateFilter(QObject):
    """Observe widget updates and invalidate cached pixmaps."""

    def __init__(self, owner: "CanvasPixmapWidgetItem") -> None:
        super().__init__(owner.widget)
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        if event.type() in {
            QEvent.Type.UpdateRequest,
            QEvent.Type.LayoutRequest,
            QEvent.Type.StyleChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.FontChange,
        }:
            try:
                self._owner.invalidate()
            except RuntimeError:
                # Owner already torn down — nothing to invalidate.
                return False
        return False


@register_canvas_item_type("canvas2d.pixmap_widget_item")
class CanvasPixmapWidgetItem(CanvasWidgetAdapterBase):
    """Render a wrapped widget into a cached pixmap and draw in world space."""

    ITEM_TYPE: str = "canvas2d.pixmap_widget_item"

    def __init__(self, widget: QWidget, world_rect: QRectF) -> None:
        super().__init__(widget, world_rect)
        self._cache_key: tuple[int, int, float, float, int] | None = None
        self._cached_pixmap: QPixmap | None = None
        self._widget_revision: int = 0
        self._update_filter = _WidgetUpdateFilter(self)
        self.widget.installEventFilter(self._update_filter)

    def set_world_rect(self, rect: QRectF) -> None:
        super().set_world_rect(rect)
        self.invalidate()

    def invalidate(self) -> None:
        self._widget_revision += 1
        self._cache_key = None
        self._cached_pixmap = None
        self.request_repaint()

    def _after_event_hook(self) -> None:
        # Pixmap snapshot may be stale after any input event mutates the widget.
        self.invalidate()

    def paint(self, ctx: CanvasPaintContext) -> None:
        self._ensure_pixmap(ctx)
        if self._cached_pixmap is None or self._cached_pixmap.isNull():
            return

        rect = self.world_rect
        zoom = ctx.view.zoom
        rot = ctx.view.rotation_radians
        cos_r = math.cos(rot)
        sin_r = math.sin(rot)
        # The canvas painter's world transform includes a Y-flip (world Y-up
        # → screen Y-down), which would mirror the pixmap.  Bypass it by
        # resetting the transform and computing a pixmap-to-screen mapping
        # directly.  In world Y-up, the visual top-left of the widget is at
        # world (rect.left(), rect.bottom()).
        kx, ky = ctx.world_to_screen((rect.left(), rect.bottom()))
        # QTransform(m11, m12, m21, m22, dx, dy):
        #   screen_x = m11*px + m21*py + dx
        #   screen_y = m12*px + m22*py + dy
        transform = QTransform(
            cos_r * zoom, sin_r * zoom,
            -sin_r * zoom, cos_r * zoom,
            kx, ky,
        )
        ctx.painter.save()
        ctx.painter.resetTransform()
        ctx.painter.setTransform(transform)
        w = max(1.0, float(rect.width()))
        h = max(1.0, float(rect.height()))
        ctx.painter.drawPixmap(
            QRectF(0.0, 0.0, w, h),
            self._cached_pixmap,
            QRectF(self._cached_pixmap.rect()),
        )
        ctx.painter.restore()

    def _ensure_pixmap(self, ctx: CanvasPaintContext) -> None:
        key = self._make_cache_key(ctx)
        if self._cached_pixmap is not None and self._cache_key == key:
            return
        self._cache_key = key
        self._cached_pixmap = self._render_pixmap(ctx)

    def _make_cache_key(self, ctx: CanvasPaintContext) -> tuple[int, int, float, float, int]:
        rect = self.world_rect
        width = max(1, int(math.ceil(max(1.0, float(rect.width())))))
        height = max(1, int(math.ceil(max(1.0, float(rect.height())))))
        zoom_bucket = self._zoom_bucket(ctx.view.zoom)
        dpr = max(1.0, float(ctx.device_pixel_ratio))
        return (width, height, zoom_bucket, dpr, self._widget_revision)

    def _render_pixmap(self, ctx: CanvasPaintContext) -> QPixmap:
        rect = self.world_rect
        logical_width = max(
            1, int(math.ceil(max(1.0, float(rect.width())))))
        logical_height = max(
            1, int(math.ceil(max(1.0, float(rect.height())))))
        self.widget.resize(logical_width, logical_height)

        scale = max(
            1.0,
            self._zoom_bucket(ctx.view.zoom) * float(ctx.device_pixel_ratio),
        )
        pixel_width = max(1, int(round(logical_width * scale)))
        pixel_height = max(1, int(round(logical_height * scale)))

        pixmap = QPixmap(pixel_width, pixel_height)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(QColor(0, 0, 0, 0))

        painter = QPainter(pixmap)
        try:
            self.widget.render(painter, QPoint(0, 0))
        finally:
            painter.end()
        return pixmap

    @staticmethod
    def _zoom_bucket(zoom: float) -> float:
        abs_zoom = max(0.001, abs(float(zoom)))
        bucket = 2.0 ** round(math.log2(abs_zoom))
        return max(0.25, min(8.0, bucket))

    def to_dict(self) -> dict | None:
        return None


__all__ = ["CanvasPixmapWidgetItem"]
