"""Anchored QWidget adapter for Canvas2D."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt
from PySide6.QtWidgets import QWidget

from lks_utils.gui_qt.canvas2d.canvas_item_registry import register_canvas_item_type
from lks_utils.gui_qt.canvas2d.canvas_widget_adapter_base import CanvasWidgetAdapterBase

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext


@register_canvas_item_type("canvas2d.anchored_widget_item")
class CanvasAnchoredWidgetItem(CanvasWidgetAdapterBase):
    """Reparent a widget into the canvas host and position it per view."""

    ITEM_TYPE: str = "canvas2d.anchored_widget_item"

    def __init__(self, widget: QWidget, world_rect: QRectF) -> None:
        super().__init__(widget, world_rect)
        self._host_widget: QWidget | None = None
        self._host_filter: _HostLifecycleFilter | None = None

    def set_world_rect(self, rect: QRectF) -> None:
        super().set_world_rect(rect)
        if self._host_widget is not None:
            self._apply_geometry_in_host()

    def invalidate(self) -> None:
        self.request_repaint()

    def paint(self, ctx: CanvasPaintContext) -> None:
        self._ensure_attached(ctx)
        if self._host_widget is not None:
            self._apply_geometry(ctx)

    def detach(self) -> None:
        """Detach the wrapped widget from the host canvas, if attached."""
        if self._host_widget is None:
            return
        if self._host_filter is not None:
            self._host_widget.removeEventFilter(self._host_filter)
        self._host_filter = None
        self.widget.hide()
        self.widget.setParent(None)
        self._host_widget = None

    def _ensure_attached(self, ctx: CanvasPaintContext) -> None:
        device = ctx.painter.device()
        if not isinstance(device, QWidget):
            return
        if self._host_widget is device and self.widget.parentWidget() is device:
            return

        if self._host_widget is not None and self._host_widget is not device:
            self.detach()

        self._host_widget = device
        self._host_filter = _HostLifecycleFilter(self)
        device.installEventFilter(self._host_filter)
        self.widget.setParent(device)
        self.widget.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation, True)
        # Ensure the widget paints its own background when embedded inside the
        # canvas (which may have a dark backdrop).  setAutoFillBackground fills
        # the widget rect with palette().window() before any custom painting,
        # matching the opaque look produced by the CanvasPixmapWidgetItem path.
        self.widget.setAutoFillBackground(True)
        self.widget.show()

    def _apply_geometry(self, ctx: CanvasPaintContext) -> None:
        rect = self.world_rect
        # World Y is up; visual top-left is at (rect.left(), rect.bottom()).
        sx, sy = ctx.world_to_screen((rect.left(), rect.bottom()))
        width = max(1, int(round(rect.width())))
        height = max(1, int(round(rect.height())))
        self.widget.resize(width, height)
        self.widget.move(QPoint(int(round(sx)), int(round(sy))))

    def _apply_geometry_in_host(self) -> None:
        if self._host_widget is None:
            return
        rect = self.world_rect
        width = max(1, int(round(rect.width())))
        height = max(1, int(round(rect.height())))
        self.widget.resize(width, height)

    def to_dict(self) -> dict | None:
        return None

    def __del__(self) -> None:
        try:
            self.detach()
        except Exception:  # noqa: BLE001
            return None


class _HostLifecycleFilter(QObject):
    """Detach anchored widget if the host canvas is destroyed."""

    def __init__(self, owner: CanvasAnchoredWidgetItem) -> None:
        super().__init__()
        self._owner = owner

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        del watched
        if event.type() == QEvent.Type.Destroy:
            self._owner.detach()
        return False


__all__ = ["CanvasAnchoredWidgetItem"]
