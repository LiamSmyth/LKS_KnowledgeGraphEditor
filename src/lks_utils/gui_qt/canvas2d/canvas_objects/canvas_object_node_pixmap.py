"""Pixmap-backed :class:`CanvasNodeObject` with a canvas-blind content ``QWidget``."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPixmap, QTransform, QWheelEvent
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_node import (
    CanvasNodeHeaderSpec,
    CanvasNodeObject,
    CanvasNodeSizeMode,
)
from lks_utils.gui_qt.canvas2d.canvas_object_registry import register_canvas_object_type
from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CANVAS_OBJECT_KEY

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext

_DOUBLE_CLICK_INTERVAL_NS = 400_000_000
_DOUBLE_CLICK_RADIUS_PX = 4
_FAR_OFF_POINT = QPoint(-100_000, -100_000)


class _ContentUpdateFilter(QObject):
    def __init__(self, owner: "CanvasNodeObjectPixmap") -> None:
        super().__init__(owner._content_widget)
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
            if self._owner._compositing_pixmap:  # noqa: SLF001
                return False
            try:
                self._owner.invalidate_content_pixmap()
            except RuntimeError:
                return False
        return False


@register_canvas_object_type("canvas2d.node_object_pixmap")
class CanvasNodeObjectPixmap(CanvasNodeObject):
    """Render a canvas-blind Qt widget into a cached pixmap at ``host_rect``.

    The entire wrapped widget is composited in Qt pixel space and blitted once
  per frame — header bands, labels, and card chrome must live in the widget tree.
    """

    OBJECT_TYPE: str = "canvas2d.node_object_pixmap"

    def __init__(
        self,
        content: QWidget,
        host_rect: QRectF,
        *,
        header: CanvasNodeHeaderSpec,
        size_mode: CanvasNodeSizeMode = CanvasNodeSizeMode.USER_OVERRIDE,
    ) -> None:
        super().__init__(
            host_rect=host_rect,
            header=header,
            size_mode=size_mode,
        )
        self._content_widget = content
        self._compositing_pixmap: bool = False
        self._cache_key: tuple[int, int, float, float, int] | None = None
        self._cached_pixmap: QPixmap | None = None
        self._widget_revision: int = 0
        self._update_filter = _ContentUpdateFilter(self)
        self._content_widget.installEventFilter(self._update_filter)

        self._active_mouse_buttons: Qt.MouseButtons = Qt.MouseButton.NoButton
        self._mouse_target: QWidget | None = None
        self._key_target: QWidget | None = None
        self._last_press_ns: int = 0
        self._last_press_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._last_press_local: QPoint = QPoint(_FAR_OFF_POINT)
        self._hovering: bool = False
        self._cursor_override_active: bool = False

        self._on_host_rect_changed()

    @property
    def content_widget(self) -> QWidget:
        return self._content_widget

    def apply_auto_host_rect(
        self,
        *,
        content_width: float,
        content_height: float,
    ) -> None:
        width = max(1.0, float(content_width))
        height = max(1.0, float(content_height))
        host = self._host_rect
        self._host_rect = QRectF(host.left(), host.bottom(), width, height)
        self._on_host_rect_changed()
        self.request_repaint(self.bounds())

    def set_header(self, header: CanvasNodeHeaderSpec) -> None:
        super().set_header(header)
        from lks_utils.gui_qt.widgets.canvas_node_card_widget import QCanvasNodeCardWidget

        widget = self._content_widget
        if isinstance(widget, QCanvasNodeCardWidget):
            widget.apply_appearance(
                title=header.title,
                subtitle=header.subtitle,
                header_bg=header.background_color,
                stroke=header.stroke_color,
                fill=header.fill_color,
                title_color=header.title_color,
                subtitle_color=header.subtitle_color or header.title_color,
                separator_color=header.separator_color or header.title_color,
                body_text=widget.body.text(),
            )
        self.invalidate_content_pixmap()

    def _on_host_rect_changed(self) -> None:
        self._resize_content_widget()
        self.invalidate_content_pixmap()

    def invalidate_content_pixmap(self) -> None:
        self._widget_revision += 1
        self._cache_key = None
        self._cached_pixmap = None
        self.request_repaint()

    def _resize_content_widget(self) -> None:
        rect = self.host_rect
        width = max(1, int(math.ceil(max(1.0, float(rect.width())))))
        height = max(1, int(math.ceil(max(1.0, float(rect.height())))))
        self._content_widget.resize(width, height)

    def paint_host_content(self, ctx: CanvasPaintContext) -> None:
        pixmap = self._ensure_host_pixmap(ctx)
        if pixmap is None or pixmap.isNull():
            return
        self._draw_pixmap_in_world_rect(ctx, self.host_rect, pixmap)

    def _ensure_host_pixmap(self, ctx: CanvasPaintContext) -> QPixmap | None:
        key = self._make_cache_key(ctx, self.host_rect, self._widget_revision)
        if self._cached_pixmap is not None and self._cache_key == key:
            return self._cached_pixmap
        self._cache_key = key
        self._cached_pixmap = self._render_widget_pixmap(
            ctx,
            self._content_widget,
            self.host_rect,
        )
        return self._cached_pixmap

    def _draw_pixmap_in_world_rect(
        self,
        ctx: CanvasPaintContext,
        rect: QRectF,
        pixmap: QPixmap,
    ) -> None:
        zoom = ctx.view.zoom
        rot = ctx.view.rotation_radians
        cos_r = math.cos(rot)
        sin_r = math.sin(rot)
        kx, ky = ctx.world_to_screen((rect.left(), rect.bottom()))
        transform = QTransform(
            cos_r * zoom,
            sin_r * zoom,
            -sin_r * zoom,
            cos_r * zoom,
            kx,
            ky,
        )
        ctx.painter.save()
        ctx.painter.resetTransform()
        ctx.painter.setTransform(transform)
        w = max(1.0, float(rect.width()))
        h = max(1.0, float(rect.height()))
        ctx.painter.drawPixmap(
            QRectF(0.0, 0.0, w, h),
            pixmap,
            QRectF(pixmap.rect()),
        )
        ctx.painter.restore()

    def _make_cache_key(
        self,
        ctx: CanvasPaintContext,
        rect: QRectF,
        revision: int,
    ) -> tuple[int, int, float, float, int]:
        width = max(1, int(math.ceil(max(1.0, float(rect.width())))))
        height = max(1, int(math.ceil(max(1.0, float(rect.height())))))
        zoom_bucket = self._zoom_bucket(ctx.view.zoom)
        dpr = max(1.0, float(ctx.device_pixel_ratio))
        return (width, height, zoom_bucket, dpr, revision)

    def _render_widget_pixmap(
        self,
        ctx: CanvasPaintContext,
        widget: QWidget,
        rect: QRectF,
    ) -> QPixmap:
        logical_width = max(1, int(math.ceil(max(1.0, float(rect.width())))))
        logical_height = max(1, int(math.ceil(max(1.0, float(rect.height())))))
        widget.resize(logical_width, logical_height)

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
        self._compositing_pixmap = True
        try:
            widget.render(painter, QPoint(0, 0))
        finally:
            self._compositing_pixmap = False
            painter.end()
        return pixmap

    @staticmethod
    def _zoom_bucket(zoom: float) -> float:
        abs_zoom = max(0.001, abs(float(zoom)))
        bucket = 2.0 ** round(math.log2(abs_zoom))
        return max(0.25, min(8.0, bucket))

    def handle_input(self, event: CanvasInputEvent) -> bool:
        if self._handle_capability_input(event):
            if event.phase in {"press", "drag", "release"} or (
                event.phase == "wheel" and event.delta is not None
            ):
                self.invalidate_content_pixmap()
            return True

        if event.action.id == CANVAS_OBJECT_KEY.id and event.phase in {"press", "release"}:
            self._dispatch_key_event(event)
            self.invalidate_content_pixmap()
            return True

        if event.phase == "wheel" and event.delta is not None:
            self._dispatch_wheel_event(event)
            self.invalidate_content_pixmap()
            return True

        if event.phase not in {"press", "drag", "release", "move"}:
            return False

        self._dispatch_mouse_event(event)
        if event.phase != "move":
            self.invalidate_content_pixmap()
        return True

    def _handle_capability_input(self, event: CanvasInputEvent) -> bool:
        for cap in reversed(self._capabilities):
            if cap.handle_input(event):
                return True
        return False

    def _dispatch_key_event(self, event: CanvasInputEvent) -> None:
        target = self._key_target if self._key_target is not None else self._content_widget
        key_event_type = (
            QEvent.Type.KeyPress if event.phase == "press" else QEvent.Type.KeyRelease
        )
        key_event = QKeyEvent(
            key_event_type,
            event.key if event.key is not None else Qt.Key.Key_unknown,
            self._qt_modifiers(event),
            event.text,
        )
        QApplication.sendEvent(target, key_event)

    def _dispatch_wheel_event(self, event: CanvasInputEvent) -> None:
        local = self._local_point(event)
        self._update_hover_state(local)
        target, local_on_target = self._event_target(local)
        global_pos = target.mapToGlobal(local_on_target)
        self._update_pointer_affordances(local, global_pos)
        wheel_event = QWheelEvent(
            QPointF(local_on_target),
            QPointF(global_pos),
            QPoint(0, 0),
            QPoint(int(round(event.delta[0])), int(round(event.delta[1]))),
            Qt.MouseButton.NoButton,
            self._qt_modifiers(event),
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QApplication.sendEvent(target, wheel_event)

    def _dispatch_mouse_event(self, event: CanvasInputEvent) -> None:
        button = self._button_for_action(event)
        local = self._local_point(event)
        self._update_hover_state(local)
        modifiers = self._qt_modifiers(event)

        if event.phase == "press":
            target, local_on_target = self._event_target(local)
            self._mouse_target = target
            self._key_target = target
            global_pos = target.mapToGlobal(local_on_target)
            self._update_pointer_affordances(local, global_pos)
            event_type = QEvent.Type.MouseButtonPress
            if self._is_double_click_candidate(event, button, local):
                event_type = QEvent.Type.MouseButtonDblClick
            self._active_mouse_buttons = self._active_mouse_buttons | button
            self._last_press_ns = event.timestamp_ns
            self._last_press_button = button
            self._last_press_local = QPoint(local)
        elif event.phase == "release":
            target, local_on_target = self._event_target(local)
            global_pos = target.mapToGlobal(local_on_target)
            self._update_pointer_affordances(local, global_pos)
            event_type = QEvent.Type.MouseButtonRelease
            self._active_mouse_buttons = self._active_mouse_buttons & ~button
            if self._active_mouse_buttons == Qt.MouseButton.NoButton:
                self._mouse_target = None
        else:
            target, local_on_target = self._event_target(local)
            global_pos = target.mapToGlobal(local_on_target)
            self._update_pointer_affordances(local, global_pos)
            event_type = QEvent.Type.MouseMove

        active_button = (
            button if event.phase in {"press", "release"} else Qt.MouseButton.NoButton
        )
        mouse_event = QMouseEvent(
            event_type,
            local_on_target.toPointF(),
            local_on_target.toPointF(),
            global_pos.toPointF(),
            active_button,
            self._active_mouse_buttons,
            modifiers,
        )
        if event.phase == "press":
            target.setFocus(Qt.FocusReason.MouseFocusReason)
        QApplication.sendEvent(target, mouse_event)

    def _local_point(self, event: CanvasInputEvent) -> QPoint:
        wx, wy = event.world_pos
        host = self.host_rect
        return QPoint(
            int(round(wx - host.left())),
            int(round(host.bottom() - wy)),
        )

    def _event_target(self, local: QPoint) -> tuple[QWidget, QPoint]:
        target = self._mouse_target
        if target is None:
            target = self._content_widget.childAt(local)
        if target is None:
            return self._content_widget, local
        if target is self._content_widget:
            return target, local
        return target, target.mapFrom(self._content_widget, local)

    def _update_hover_state(self, local: QPoint) -> None:
        host = self.host_rect
        inside = QRectF(0.0, 0.0, host.width(), host.height()).contains(
            float(local.x()),
            float(local.y()),
        )
        if inside and not self._hovering:
            QApplication.sendEvent(self._content_widget, QEvent(QEvent.Type.Enter))
            self._hovering = True
        elif not inside and self._hovering:
            QApplication.sendEvent(self._content_widget, QEvent(QEvent.Type.Leave))
            self._hovering = False
            QToolTip.hideText()
            self._clear_cursor_override()

    def _clear_cursor_override(self) -> None:
        if self._cursor_override_active:
            QApplication.restoreOverrideCursor()
            self._cursor_override_active = False

    def _update_pointer_affordances(self, local: QPoint, global_pos: QPoint) -> None:
        if not self._hovering:
            return
        target = self._content_widget.childAt(local)
        if target is None:
            target = self._content_widget

        tooltip = target.toolTip()
        if tooltip:
            QToolTip.showText(global_pos, tooltip, self._content_widget)
        else:
            QToolTip.hideText()

        target_cursor = target.cursor()
        if target_cursor.shape() != Qt.CursorShape.ArrowCursor:
            if self._cursor_override_active:
                QApplication.changeOverrideCursor(target_cursor)
            else:
                QApplication.setOverrideCursor(target_cursor)
                self._cursor_override_active = True
        else:
            self._clear_cursor_override()

    @staticmethod
    def _button_for_action(event: CanvasInputEvent) -> Qt.MouseButton:
        if event.action.id == "canvas2d.input.secondary":
            return Qt.MouseButton.RightButton
        return Qt.MouseButton.LeftButton

    @staticmethod
    def _qt_modifiers(event: CanvasInputEvent) -> Qt.KeyboardModifier:
        from lks_utils.input import Modifier

        qt_mods = Qt.KeyboardModifier.NoModifier
        if Modifier.SHIFT in event.modifiers:
            qt_mods = qt_mods | Qt.KeyboardModifier.ShiftModifier
        if Modifier.CTRL in event.modifiers:
            qt_mods = qt_mods | Qt.KeyboardModifier.ControlModifier
        if Modifier.ALT in event.modifiers:
            qt_mods = qt_mods | Qt.KeyboardModifier.AltModifier
        if Modifier.META in event.modifiers:
            qt_mods = qt_mods | Qt.KeyboardModifier.MetaModifier
        return qt_mods

    def _is_double_click_candidate(
        self,
        event: CanvasInputEvent,
        button: Qt.MouseButton,
        local: QPoint,
    ) -> bool:
        if self._last_press_button != button:
            return False
        dt_ns = event.timestamp_ns - self._last_press_ns
        if dt_ns <= 0 or dt_ns > _DOUBLE_CLICK_INTERVAL_NS:
            return False
        dx = abs(local.x() - self._last_press_local.x())
        dy = abs(local.y() - self._last_press_local.y())
        return dx <= _DOUBLE_CLICK_RADIUS_PX and dy <= _DOUBLE_CLICK_RADIUS_PX

    def to_dict(self) -> dict | None:
        return None


__all__ = ["CanvasNodeObjectPixmap"]
