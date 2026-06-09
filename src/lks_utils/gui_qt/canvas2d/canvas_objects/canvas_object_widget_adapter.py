"""Shared base class for canvas-adapted Qt widgets.

The base owns:
  * the wrapped (canvas-blind) ``QWidget`` and its world-space rect;
  * a concrete ``handle_input`` implementation that synthesizes Qt mouse,
    wheel, and key events on the wrapped widget;
  * shared interaction state (active buttons, focused mouse/key targets,
    double-click candidacy, hover state, cursor override).

Subclasses provide their own ``paint`` and may override ``invalidate``
and ``_after_event_hook`` (e.g. to bust a pixmap cache).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QToolTip, QWidget

from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CANVAS_OBJECT_KEY
from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext


_DOUBLE_CLICK_INTERVAL_NS = 400_000_000
_DOUBLE_CLICK_RADIUS_PX = 4
_FAR_OFF_POINT = QPoint(-100_000, -100_000)


class CanvasObjectWidgetAdapter(CanvasObject, ABC):
    """Base class for adapter items that own a canvas-blind ``QWidget``."""

    def __init__(self, widget: QWidget, world_rect: QRectF) -> None:
        super().__init__()
        self._widget: QWidget = widget
        self._world_rect: QRectF = QRectF(world_rect)
        self._active_mouse_buttons: Qt.MouseButtons = Qt.MouseButton.NoButton
        self._mouse_target: QWidget | None = None
        self._key_target: QWidget | None = None
        self._last_press_ns: int = 0
        self._last_press_button: Qt.MouseButton = Qt.MouseButton.NoButton
        self._last_press_local: QPoint = QPoint(_FAR_OFF_POINT)
        self._hovering: bool = False
        self._cursor_override_active: bool = False

    @property
    def widget(self) -> QWidget:
        """Wrapped canvas-blind widget."""
        return self._widget

    @property
    def world_rect(self) -> QRectF:
        """World-space rectangle that governs adapter sizing and placement."""
        return QRectF(self._world_rect)

    def set_world_rect(self, rect: QRectF) -> None:
        """Update the authoritative world-space rectangle."""
        self._world_rect = QRectF(rect)
        self.request_repaint()

    def invalidate(self) -> None:
        """Subclasses override when they maintain internal caches."""
        return None

    def bounds(self) -> AABB:
        rect = self._world_rect
        return AABB(rect.left(), rect.top(), rect.right(), rect.bottom())

    # ------------------------------------------------------------------ #
    # Input routing
    # ------------------------------------------------------------------ #

    def handle_input(self, event: CanvasInputEvent) -> bool:
        if event.action.id == CANVAS_OBJECT_KEY.id and event.phase in {"press", "release"}:
            self._dispatch_key_event(event)
            self._after_event_hook()
            return True

        if event.phase == "wheel" and event.delta is not None:
            self._dispatch_wheel_event(event)
            self._after_event_hook()
            return True

        if event.phase not in {"press", "drag", "release", "move"}:
            return False

        self._dispatch_mouse_event(event)
        self._after_event_hook()
        return True

    def _after_event_hook(self) -> None:
        """Subclass hook fired after each dispatched input event."""
        return None

    # ------------------------------------------------------------------ #
    # Event synthesis helpers
    # ------------------------------------------------------------------ #

    def _dispatch_key_event(self, event: CanvasInputEvent) -> None:
        target = self._key_target if self._key_target is not None else self.widget
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
        rect = self._world_rect
        local_x = int(round(event.world_pos[0] - rect.left()))
        # World Y is up; visual widget-top is at rect.bottom() in world space.
        local_y = int(round(rect.bottom() - event.world_pos[1]))
        return QPoint(local_x, local_y)

    def _event_target(self, local: QPoint) -> tuple[QWidget, QPoint]:
        target = self._mouse_target
        if target is None:
            target = self.widget.childAt(local)
        if target is None:
            return self.widget, local
        if target is self.widget:
            return target, local
        return target, target.mapFrom(self.widget, local)

    def _update_hover_state(self, local: QPoint) -> None:
        rect = self._world_rect
        inside = QRectF(0.0, 0.0, rect.width(), rect.height()).contains(
            float(local.x()),
            float(local.y()),
        )
        if inside and not self._hovering:
            QApplication.sendEvent(self.widget, QEvent(QEvent.Type.Enter))
            self._hovering = True
        elif not inside and self._hovering:
            QApplication.sendEvent(self.widget, QEvent(QEvent.Type.Leave))
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
        target = self.widget.childAt(local)
        if target is None:
            target = self.widget

        tooltip = target.toolTip()
        if tooltip:
            QToolTip.showText(global_pos, tooltip, self.widget)
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
    def _qt_modifiers(event: CanvasInputEvent) -> Qt.KeyboardModifiers:
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

    @abstractmethod
    def paint(self, ctx: CanvasPaintContext) -> None:
        raise NotImplementedError


__all__ = ["CanvasObjectWidgetAdapter"]

