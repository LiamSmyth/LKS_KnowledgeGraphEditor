"""QWidget host for a Canvas2D QOpenGLWindow backend.

This provides a QWidget-compatible surface for side-by-side A/B testing
against Canvas2DGLWidget in the full demo.
"""
from __future__ import annotations

import time
from typing import Callable
from typing import Any

from PySide6.QtCore import QEvent, QRect, QTimer, Signal
from PySide6.QtGui import (
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QResizeEvent,
    QTabletEvent,
    QWheelEvent,
)
from PySide6.QtOpenGL import QOpenGLWindow
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lks_utils.gpu.gpu_context import GPUContext
from lks_utils.gui_qt.canvas2d.actions import (
    CANVAS_FIT_CONTENT,
    CANVAS_PAN,
    CANVAS_PRIMARY,
    CANVAS_RESET_VIEW,
    CANVAS_RESET_ZOOM,
    CANVAS_ROTATE,
    CANVAS_SECONDARY,
    CANVAS_ZOOM_IN,
    CANVAS_ZOOM_OUT,
)
from lks_utils.gui_qt.canvas2d.canvas_input_event import CANVAS_MOVE
from lks_utils.gui_qt.canvas2d.camera2d import Camera2D
from lks_utils.gui_qt.canvas2d.canvas2d_gpu_overlay_renderer import (
    Canvas2DGPUOverlayRenderer,
)
from lks_utils.gui_qt.canvas2d.canvas2d_renderer import Canvas2DRenderer, OverlayTiming
from lks_utils.gui_qt.canvas2d.canvas2d_widget import (
    Canvas2DWidget,
    _CanvasHoverTooltipPopup,
)
from lks_utils.gui_qt.canvas2d.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.input import GestureKind, get_default_bindings
from lks_utils.input.qt_adapter import (
    qt_button_to_logical,
    qt_modifiers_to_logical,
    wheel_event_pair,
)

try:
    import moderngl

    HAS_CANVAS2D_GL_WINDOW = True
except ImportError:
    HAS_CANVAS2D_GL_WINDOW = False


class _Canvas2DGLWindowSurface(QOpenGLWindow):
    """OpenGL window surface with Canvas2D scene + renderer pipeline."""

    view_changed = Signal(object)
    item_added = Signal(object)
    item_removed = Signal(object)
    item_changed = Signal(object, object)
    cursor_world_pos = Signal(float, float)
    selection_changed = Signal()
    modified_changed = Signal(bool)
    frame_timings_ready = Signal(object)

    _MIN_ZOOM: float = Canvas2DWidget._MIN_ZOOM
    _MAX_ZOOM: float = Canvas2DWidget._MAX_ZOOM
    _ZOOM_STEP: float = Canvas2DWidget._ZOOM_STEP
    _ROTATION_SNAP_DEG: float = Canvas2DWidget._ROTATION_SNAP_DEG
    _HOVER_TOOLTIP_DELAY_MS: int = Canvas2DWidget._HOVER_TOOLTIP_DELAY_MS
    GOTO_DURATION_MS: int = Canvas2DWidget.GOTO_DURATION_MS

    def __init__(self, *, swap_interval: int = 0) -> None:
        super().__init__()
        if not HAS_CANVAS2D_GL_WINDOW:
            raise RuntimeError(
                "moderngl is required for Canvas2DGLWindowWidget")
        fmt = self.format()
        fmt.setVersion(3, 3)
        resolved_swap_interval = max(0, int(swap_interval))
        fmt.setSwapInterval(resolved_swap_interval)
        self.setFormat(fmt)
        self._swap_interval = resolved_swap_interval

        self.scene: Scene2D = Scene2D(self)
        self.camera: Camera2D = Camera2D(self)
        self.renderer: Canvas2DRenderer = Canvas2DRenderer()
        self.ctx = None
        self._gpu_context: GPUContext | None = None
        self._gpu_overlay_renderer: Canvas2DGPUOverlayRenderer | None = None
        self._is_modified: bool = False
        self._continuous_update_enabled: bool = False
        self._gpu_timer_profiling_enabled: bool = False
        self._drag_action: str | None = None
        self._drag_screen_anchor: tuple[float, float] | None = None
        self._drag_view_anchor: ViewTransform | None = None
        self._primary_item = None
        self._cursor_screen: tuple[float, float] | None = None
        self._hover_tooltip_item = None
        self._hover_tooltip_text: str | None = None
        self._hover_tooltip_popup = _CanvasHoverTooltipPopup()
        self._hover_tooltip_timer = QTimer(self)
        self._hover_tooltip_timer.setSingleShot(True)
        self._hover_tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._pending_hover_tooltip_item = None
        self._pending_hover_tooltip_text = None
        self._pending_hover_tooltip_global_pos = None
        self._zoom_alpha: float = 0.35
        self._pan_alpha: float = 0.5

        self.camera.view_changed.connect(self._on_camera_view_changed)
        self.scene.item_added.connect(self._on_scene_item_added)
        self.scene.item_removed.connect(self._on_scene_item_removed)
        self.scene.item_changed.connect(self._on_scene_item_changed)
        self.scene.dirty_changed.connect(self.update)
        self.scene.selection_changed.connect(self.selection_changed)

    @property
    def last_frame_timings(self):
        return self.renderer.last_frame_timings

    def initializeGL(self) -> None:
        self.ctx = moderngl.create_context()
        self._gpu_context = GPUContext(self.ctx)
        self._gpu_overlay_renderer = Canvas2DGPUOverlayRenderer(self.ctx)
        for item in self.scene.items():
            item.on_gpu_context_changed(self._gpu_context)
        for overlay in self.scene.overlays():
            overlay.on_gpu_context_changed(self._gpu_context)

    def paintGL(self) -> None:
        if self.ctx is None or self._gpu_overlay_renderer is None:
            return
        frame_start = time.perf_counter()
        dpr = max(1.0, float(self.devicePixelRatio()))
        width_px = max(1, int(round(float(self.width()) * dpr)))
        height_px = max(1, int(round(float(self.height()) * dpr)))

        target_fbo = self.ctx.detect_framebuffer(
            self.defaultFramebufferObject())
        target_fbo.use()
        gpu_bg_start = time.perf_counter()
        bg_overlay_timings: list[tuple[str, float, float]] = []
        consumed_bg = self._gpu_overlay_renderer.render(
            self.scene,
            self.camera.view(),
            (width_px, height_px),
            (float(self.width()), float(self.height())),
            dpr,
            layer="background",
            timing_sink=bg_overlay_timings,
            gpu_timing=self._gpu_timer_profiling_enabled,
        )
        gpu_bg_ms = (time.perf_counter() - gpu_bg_start) * 1000.0
        consumed_fg = self._gpu_overlay_renderer.planned_consumed(
            self.scene,
            layer="foreground",
        )
        consumed = consumed_bg | consumed_fg

        qp_init_t = time.perf_counter()
        painter = QPainter(self)
        qp_init_ms = (time.perf_counter() - qp_init_t) * 1000.0
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.renderer.paint(
            self.scene,
            self.camera,
            painter,
            QRect(0, 0, int(self.width()), int(self.height())),
            paint_background=False,
            excluded_overlays=consumed,
        )
        qp_flush_t = time.perf_counter()
        painter.end()
        qp_flush_ms = (time.perf_counter() - qp_flush_t) * 1000.0

        if consumed_fg:
            target_fbo.use()
            gpu_fg_start = time.perf_counter()
            fg_overlay_timings: list[tuple[str, float, float]] = []
            self._gpu_overlay_renderer.render(
                self.scene,
                self.camera.view(),
                (width_px, height_px),
                (float(self.width()), float(self.height())),
                dpr,
                layer="foreground",
                timing_sink=fg_overlay_timings,
                gpu_timing=self._gpu_timer_profiling_enabled,
            )
            gpu_fg_ms = (time.perf_counter() - gpu_fg_start) * 1000.0
        else:
            fg_overlay_timings = []
            gpu_fg_ms = 0.0

        frame_end = time.perf_counter()
        timings = self.renderer.last_frame_timings
        if timings is not None:
            timings.total_ms = (frame_end - frame_start) * 1000.0
            timings.frame_timestamp = frame_end
            timings.frame_start_timestamp = frame_start
            timings.frame_end_timestamp = frame_end
            timings.qpainter_init_ms = qp_init_ms
            timings.qpainter_flush_ms = qp_flush_ms
            timings.background_ms += gpu_bg_ms
            if consumed_bg:
                timings.overlay_timings.append(
                    OverlayTiming(
                        name=f"GPU overlays (bg:{len(consumed_bg)})",
                        z_order=-1000,
                        duration_ms=gpu_bg_ms,
                    )
                )
            for name, cpu_submit_ms, gpu_elapsed_ms in bg_overlay_timings:
                timings.overlay_timings.append(
                    OverlayTiming(
                        name=f"GPU {name} CPU submit (bg)",
                        z_order=-1001,
                        duration_ms=cpu_submit_ms,
                    )
                )
                if gpu_elapsed_ms > 0.0:
                    timings.overlay_timings.append(
                        OverlayTiming(
                            name=f"GPU {name} elapsed (bg)",
                            z_order=-1002,
                            duration_ms=gpu_elapsed_ms,
                        )
                    )
            if consumed_fg and gpu_fg_ms > 0.0:
                timings.overlay_timings.append(
                    OverlayTiming(
                        name=f"GPU overlays (fg:{len(consumed_fg)})",
                        z_order=1000,
                        duration_ms=gpu_fg_ms,
                    )
                )
            for name, cpu_submit_ms, gpu_elapsed_ms in fg_overlay_timings:
                timings.overlay_timings.append(
                    OverlayTiming(
                        name=f"GPU {name} CPU submit (fg)",
                        z_order=1001,
                        duration_ms=cpu_submit_ms,
                    )
                )
                if gpu_elapsed_ms > 0.0:
                    timings.overlay_timings.append(
                        OverlayTiming(
                            name=f"GPU {name} elapsed (fg)",
                            z_order=1002,
                            duration_ms=gpu_elapsed_ms,
                        )
                    )
            self.frame_timings_ready.emit(timings)

        if self._continuous_update_enabled and self.isExposed():
            self.update()

    def set_swap_interval(self, interval: int) -> None:
        value = max(0, int(interval))
        if value == self._swap_interval:
            return
        self._swap_interval = value
        fmt = self.format()
        fmt.setSwapInterval(value)
        self.setFormat(fmt)

    def set_continuous_update_enabled(self, enabled: bool) -> None:
        self._continuous_update_enabled = bool(enabled)
        if self._continuous_update_enabled and self.isExposed():
            self.update()

    def set_gpu_timer_profiling_enabled(self, enabled: bool) -> None:
        self._gpu_timer_profiling_enabled = bool(enabled)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.scene.dirty_tracker().mark(None)
        super().resizeEvent(event)

    def exposeEvent(self, event) -> None:  # noqa: ANN001
        super().exposeEvent(event)
        if self._continuous_update_enabled and self.isExposed():
            self.update()

    def hideEvent(self, event) -> None:  # noqa: ANN001
        super().hideEvent(event)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._continuous_update_enabled = False
        super().closeEvent(event)

    def add_item(self, item, z_order: int | None = None) -> None:  # noqa: ANN001
        if self._gpu_context is not None:
            item.on_gpu_context_changed(self._gpu_context)
        self.scene.add_item(item, z_order)

    def add_overlay(self, overlay) -> None:  # noqa: ANN001
        if self._gpu_context is not None:
            overlay.on_gpu_context_changed(self._gpu_context)
        self.scene.add_overlay(overlay)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._clear_hover_tooltip()
        button = qt_button_to_logical(event.button())
        if button is None:
            QOpenGLWindow.mousePressEvent(self, event)
            return
        mods = qt_modifiers_to_logical(event.modifiers())
        screen = (event.position().x(), event.position().y())
        bindings = get_default_bindings()

        if bindings.matches_mouse(CANVAS_PAN.id, button, mods, GestureKind.DRAG):
            if not self.camera.is_locked:
                self._begin_drag(CANVAS_PAN.id, screen)
            event.accept()
            return
        if bindings.matches_mouse(CANVAS_ROTATE.id, button, mods, GestureKind.DRAG):
            if not self.camera.is_locked:
                self._begin_drag(CANVAS_ROTATE.id, screen)
            event.accept()
            return

        if bindings.matches_mouse(CANVAS_PRIMARY.id, button, mods, GestureKind.PRESS):
            world_pos = self._screen_to_world(*screen)
            canvas_event = self._make_event(
                CANVAS_PRIMARY, "press", screen, mods)
            consumer = self._route_to_topmost(world_pos, canvas_event)
            if consumer is not None:
                self._primary_item = consumer
                event.accept()
                return

        if bindings.matches_mouse(CANVAS_SECONDARY.id, button, mods, GestureKind.PRESS):
            world_pos = self._screen_to_world(*screen)
            canvas_event = self._make_event(
                CANVAS_SECONDARY, "press", screen, mods)
            self._route_to_topmost(world_pos, canvas_event)
            event.accept()
            return

        QOpenGLWindow.mousePressEvent(self, event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        screen = (event.position().x(), event.position().y())
        self._cursor_screen = screen
        world_pos = self._screen_to_world(*screen)
        self.cursor_world_pos.emit(world_pos[0], world_pos[1])

        if self._drag_action is not None and self._drag_screen_anchor is not None:
            self._clear_hover_tooltip()
            self._handle_drag_motion(screen)
            event.accept()
            return

        if self._primary_item is not None:
            self._clear_hover_tooltip()
            mods = qt_modifiers_to_logical(event.modifiers())
            canvas_event = self._make_event(
                CANVAS_PRIMARY, "drag", screen, mods)
            self._primary_item.handle_input(canvas_event)
            event.accept()
            return

        mods = qt_modifiers_to_logical(event.modifiers())
        canvas_event = self._make_event(CANVAS_MOVE, "move", screen, mods)
        self._update_hover_tooltip(screen, canvas_event.world_pos)
        self.update()
        QOpenGLWindow.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        screen = (event.position().x(), event.position().y())
        if self._drag_action is not None:
            self._end_drag(screen)
            event.accept()
            return
        if self._primary_item is not None:
            mods = qt_modifiers_to_logical(event.modifiers())
            canvas_event = self._make_event(
                CANVAS_PRIMARY, "release", screen, mods)
            self._primary_item.handle_input(canvas_event)
            self._primary_item = None
            event.accept()
            return
        QOpenGLWindow.mouseReleaseEvent(self, event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        mods, direction = wheel_event_pair(event)
        bindings = get_default_bindings()
        screen = (event.position().x(), event.position().y())
        if bindings.matches_wheel(CANVAS_ZOOM_IN.id, mods, direction):
            if not self.camera.is_locked:
                self._zoom_about(screen, self._ZOOM_STEP)
            event.accept()
            return
        if bindings.matches_wheel(CANVAS_ZOOM_OUT.id, mods, direction):
            if not self.camera.is_locked:
                self._zoom_about(screen, 1.0 / self._ZOOM_STEP)
            event.accept()
            return
        QOpenGLWindow.wheelEvent(self, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        sequence = QKeySequence(event.keyCombination()).toString()
        bindings = get_default_bindings()
        if bindings.matches_key(CANVAS_RESET_VIEW.id, sequence):
            if not self.camera.is_locked:
                self.reset_view(animate=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_FIT_CONTENT.id, sequence):
            if not self.camera.is_locked:
                self.fit_to_content(animate=True)
            event.accept()
            return
        if bindings.matches_key(CANVAS_RESET_ZOOM.id, sequence):
            if not self.camera.is_locked:
                self.reset_zoom(animate=True)
            event.accept()
            return
        QOpenGLWindow.keyPressEvent(self, event)

    def leaveEvent(self, event: QEvent) -> None:
        self._cursor_screen = None
        self._clear_hover_tooltip()
        self.update()
        QOpenGLWindow.leaveEvent(self, event)

    def tabletEvent(self, event: QTabletEvent) -> None:
        screen = (event.position().x(), event.position().y())
        mods = qt_modifiers_to_logical(event.modifiers())
        event_type = event.type()
        world_pos = self._screen_to_world(*screen)
        bindings = get_default_bindings()

        if event_type == QEvent.Type.TabletPress:
            button = qt_button_to_logical(event.button())
            if button is not None:
                if bindings.matches_mouse(CANVAS_PAN.id, button, mods, GestureKind.DRAG):
                    if not self.camera.is_locked:
                        self._begin_drag(CANVAS_PAN.id, screen)
                    event.accept()
                    return
                if bindings.matches_mouse(CANVAS_ROTATE.id, button, mods, GestureKind.DRAG):
                    if not self.camera.is_locked:
                        self._begin_drag(CANVAS_ROTATE.id, screen)
                    event.accept()
                    return
            canvas_event = self._make_event(
                CANVAS_PRIMARY,
                "press",
                screen,
                mods,
                pressure=float(event.pressure()),
                is_tablet=True,
            )
            consumer = self._route_to_topmost(world_pos, canvas_event)
            if consumer is not None:
                self._primary_item = consumer
                event.accept()
                return

        elif event_type == QEvent.Type.TabletMove:
            self._cursor_screen = screen
            self.cursor_world_pos.emit(world_pos[0], world_pos[1])
            if self._drag_action is not None:
                self._clear_hover_tooltip()
                self._handle_drag_motion(screen)
                event.accept()
                return
            if self._primary_item is not None:
                self._clear_hover_tooltip()
                canvas_event = self._make_event(
                    CANVAS_PRIMARY,
                    "drag",
                    screen,
                    mods,
                    pressure=float(event.pressure()),
                    is_tablet=True,
                )
                self._primary_item.handle_input(canvas_event)
                event.accept()
                return
            self._update_hover_tooltip(screen, world_pos)
            self.update()

        elif event_type == QEvent.Type.TabletRelease:
            if self._drag_action is not None:
                self._end_drag(screen)
                event.accept()
                return
            if self._primary_item is not None:
                canvas_event = self._make_event(
                    CANVAS_PRIMARY,
                    "release",
                    screen,
                    mods,
                    pressure=float(event.pressure()),
                    is_tablet=True,
                )
                self._primary_item.handle_input(canvas_event)
                self._primary_item = None
                event.accept()
                return

        QOpenGLWindow.tabletEvent(self, event)

    def _on_scene_item_added(self, item) -> None:  # noqa: ANN001
        if self._gpu_context is not None:
            item.on_gpu_context_changed(self._gpu_context)
        self.item_added.emit(item)
        self._set_modified(True)


for _name in (
    "input_scope",
    "remove_item",
    "items",
    "remove_overlay",
    "overlays",
    "register_hud_provider",
    "hud_strings",
    "select_item",
    "deselect_item",
    "clear_selection",
    "selected_items",
    "is_modified",
    "mark_saved",
    "view",
    "set_view",
    "reset_view",
    "reset_zoom",
    "fit_to_aabb",
    "fit_to_content",
    "go_to",
    "cancel_view_animation",
    "is_view_animating",
    "fly_to",
    "save_view",
    "restore_view",
    "delete_bookmark",
    "bookmarks",
    "to_document",
    "load_document",
    "save_json",
    "load_json",
    "_on_camera_view_changed",
    "_on_scene_item_removed",
    "_on_scene_item_changed",
    "_set_modified",
    "_screen_to_world",
    "_make_event",
    "_route_to_topmost",
    "_clear_hover_tooltip",
    "_show_hover_tooltip",
    "_update_hover_tooltip",
    "_begin_drag",
    "_handle_drag_motion",
    "_end_drag",
    "_zoom_about",
    "_set_texture_overlay_pivot",
    "_clear_texture_overlay_pivot_lock",
):
    setattr(_Canvas2DGLWindowSurface, _name, getattr(Canvas2DWidget, _name))


class Canvas2DGLWindowWidget(QWidget):
    """QWidget wrapper for a Canvas2D QOpenGLWindow backend."""

    view_changed = Signal(object)
    item_added = Signal(object)
    item_removed = Signal(object)
    item_changed = Signal(object, object)
    cursor_world_pos = Signal(float, float)
    selection_changed = Signal()
    modified_changed = Signal(bool)
    frame_timings_ready = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, swap_interval: int = 0) -> None:
        super().__init__(parent)
        self._window = _Canvas2DGLWindowSurface(swap_interval=swap_interval)
        self._container = QWidget.createWindowContainer(self._window, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._container)

        self._window.view_changed.connect(self.view_changed)
        self._window.item_added.connect(self.item_added)
        self._window.item_removed.connect(self.item_removed)
        self._window.item_changed.connect(self.item_changed)
        self._window.cursor_world_pos.connect(self.cursor_world_pos)
        self._window.selection_changed.connect(self.selection_changed)
        self._window.modified_changed.connect(self.modified_changed)
        self._window.frame_timings_ready.connect(self.frame_timings_ready)

    @property
    def scene(self) -> Scene2D:
        return self._window.scene

    @property
    def camera(self) -> Camera2D:
        return self._window.camera

    @property
    def renderer(self) -> Canvas2DRenderer:
        return self._window.renderer

    @property
    def last_frame_timings(self):
        return self._window.last_frame_timings

    def grabFramebuffer(self):  # noqa: N802
        return self._window.grabFramebuffer()

    def repaint(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self._window.update()
        super().update()

    def set_swap_interval(self, interval: int) -> None:
        self._window.set_swap_interval(interval)

    def set_continuous_update_enabled(self, enabled: bool) -> None:
        self._window.set_continuous_update_enabled(enabled)

    def set_gpu_timer_profiling_enabled(self, enabled: bool) -> None:
        self._window.set_gpu_timer_profiling_enabled(enabled)

    def update(self) -> None:  # noqa: A003
        self._window.update()
        super().update()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._window, name)


__all__ = ["Canvas2DGLWindowWidget", "HAS_CANVAS2D_GL_WINDOW"]
