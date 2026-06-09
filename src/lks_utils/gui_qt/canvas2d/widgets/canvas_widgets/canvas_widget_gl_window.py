"""QWidget host for a Canvas2D QOpenGLWindow backend.

This provides a QWidget-compatible surface for side-by-side A/B testing
against Canvas2DGLWidget in the full demo.
"""
from __future__ import annotations

import time
from typing import Callable
from typing import Any

from PySide6.QtCore import QObject, QRect, QTimer, Signal
from PySide6.QtGui import QPainter, QResizeEvent
from PySide6.QtOpenGL import QOpenGLWindow
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lks_utils.gpu.gpu_context import GPUContext
from lks_utils.gui_qt.canvas2d.core.camera2d import Camera2D
from lks_utils.gui_qt.canvas2d.render.canvas_gpu_overlay_renderer import (
    Canvas2DGPUOverlayRenderer,
)
from lks_utils.gui_qt.canvas2d.render.canvas_renderer import Canvas2DRenderer, OverlayTiming
from lks_utils.gui_qt.canvas2d.widgets._drag_controller import DragControllerMixin
from lks_utils.gui_qt.canvas2d.widgets._hover_tooltip import (
    HoverTooltipMixin,
    _CanvasHoverTooltipPopup,
)
from lks_utils.gui_qt.canvas2d.widgets._input_routing import InputRoutingMixin
from lks_utils.gui_qt.canvas2d.widgets.canvas_widget import Canvas2DWidget
from lks_utils.gui_qt.canvas2d.widgets.canvas_widget_policies import CanvasWidgetPolicies
from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform

try:
    import moderngl

    HAS_CANVAS2D_GL_WINDOW = True
except ImportError:
    HAS_CANVAS2D_GL_WINDOW = False


class _GLWindowObjectHost(QObject):
    """Owns QObject children for a :class:`QOpenGLWindow` canvas surface.

    ``QOpenGLWindow`` is a ``QWindow``, not a ``QWidget``; PySide rejects
    many ``QObject`` subclasses when parented directly to it.
    """


class _Canvas2DGLWindowSurface(
    HoverTooltipMixin,
    DragControllerMixin,
    InputRoutingMixin,
    QOpenGLWindow,
):
    """OpenGL window surface with Canvas2D scene + renderer pipeline."""

    view_changed = Signal(object)
    object_added = Signal(object)
    object_removed = Signal(object)
    object_changed = Signal(object, object)
    cursor_world_pos = Signal(float, float)
    selection_changed = Signal()
    active_selection_changed = Signal(object)
    modified_changed = Signal(bool)
    objects_moved = Signal(list)
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

        self._qobject_host = _GLWindowObjectHost()
        self.scene: Scene2D = Scene2D(self._qobject_host)
        self.camera: Camera2D = Camera2D(self._qobject_host)
        self.renderer: Canvas2DRenderer = Canvas2DRenderer()
        self.ctx = None
        self._gpu_context: GPUContext | None = None
        self._gpu_overlay_renderer: Canvas2DGPUOverlayRenderer | None = None
        self._is_modified: bool = False
        self._continuous_update_enabled: bool = False
        self._gpu_timer_profiling_enabled: bool = False

        self.capabilities = CanvasWidgetPolicies()
        self._init_drag_controller()
        self._init_input_routing()
        self.history = (
            self.create_command_history()
            if self.capabilities.allow_undo_redo
            else None
        )

        self._hover_tooltip_object = None
        self._hover_tooltip_text: str | None = None
        self._hover_tooltip_popup = _CanvasHoverTooltipPopup()
        self._hover_tooltip_timer = QTimer(self._qobject_host)
        self._hover_tooltip_timer.setSingleShot(True)
        self._hover_tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._pending_hover_tooltip_object = None
        self._pending_hover_tooltip_text = None
        self._pending_hover_tooltip_global_pos = None

        self.camera.view_changed.connect(self._on_camera_view_changed)
        self.scene.object_added.connect(self._on_scene_object_added)
        self.scene.object_removed.connect(self._on_scene_object_removed)
        self.scene.object_changed.connect(self._on_scene_object_changed)
        self.scene.dirty_changed.connect(self.update)
        self.scene.selection_changed.connect(self.selection_changed)
        self.scene.active_selection_changed.connect(self.active_selection_changed)

    @property
    def last_frame_timings(self):
        return self.renderer.last_frame_timings

    def initializeGL(self) -> None:
        self.ctx = moderngl.create_context()
        self._gpu_context = GPUContext(self.ctx)
        self._gpu_overlay_renderer = Canvas2DGPUOverlayRenderer(self.ctx)
        for obj in self.scene.objects():
            obj.on_gpu_context_changed(self._gpu_context)
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
            if self._needs_continuous_repaint():
                self.update()

    def _needs_continuous_repaint(self) -> bool:
        """Return whether the GL window should schedule another frame."""
        if self.scene.dirty_tracker().is_dirty():
            return True
        if self.camera.is_view_animating():
            return True
        if self._drag_action is not None:
            return True
        if self._primary_object is not None:
            return True
        if self._dragging_objects:
            return True
        if self._rubber_band_overlay is not None:
            return True
        return False

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

    def add_object(self, obj, z_order: int | None = None) -> None:  # noqa: ANN001
        if self._gpu_context is not None:
            obj.on_gpu_context_changed(self._gpu_context)
        self.scene.add_object(obj, z_order)

    def add_overlay(self, overlay) -> None:  # noqa: ANN001
        if self._gpu_context is not None:
            overlay.on_gpu_context_changed(self._gpu_context)
        self.scene.add_overlay(overlay)

    def _on_scene_object_added(self, obj) -> None:  # noqa: ANN001
        from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
            CapabilityHostObject,
        )

        if isinstance(obj, CapabilityHostObject):
            obj.bind_host_services(
                scene=self.scene,
                command_history=getattr(self, "history", None),
                view_zoom=lambda: self.camera.view().zoom,
                view_transform=lambda: self.camera.view(),
                viewport_size_px=lambda: (float(self.width()), float(self.height())),
            )
        if self._gpu_context is not None:
            obj.on_gpu_context_changed(self._gpu_context)
        self.object_added.emit(obj)
        self._set_modified(True)


for _name in (
    "input_scope",
    "add_object",
    "remove_object",
    "objects",
    "remove_overlay",
    "overlays",
    "register_hud_provider",
    "hud_strings",
    "select_object",
    "deselect_object",
    "toggle_object_selection",
    "clear_selection",
    "selected_objects",
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
    "_on_scene_object_removed",
    "_set_modified",
):
    setattr(_Canvas2DGLWindowSurface, _name, getattr(Canvas2DWidget, _name))


def _gl_create_command_history(self: _Canvas2DGLWindowSurface):
    from lks_utils.gui_qt.canvas2d.interaction.command_history import CommandHistory

    return CommandHistory(self._qobject_host)


_Canvas2DGLWindowSurface.create_command_history = _gl_create_command_history  # type: ignore[method-assign]


def _gl_schedule_repaint(self: _Canvas2DGLWindowSurface) -> None:
    """Repaint only when interaction or scene dirt requires new pixels.

    The QWidget canvas can afford an ``update()`` on every hover move; the
    GL-window path composites Qt pixmaps through ``paintGL`` and must avoid
    full-frame redraws for cursor-only motion.
    """
    if self._needs_continuous_repaint():
        self.update()


def _gl_on_scene_object_changed(
    self: _Canvas2DGLWindowSurface, obj, region
) -> None:  # noqa: ANN001
    self.object_changed.emit(obj, region)
    if obj.to_dict() is not None:
        self._set_modified(True)


_Canvas2DGLWindowSurface._schedule_repaint = _gl_schedule_repaint  # type: ignore[method-assign]
_Canvas2DGLWindowSurface._on_scene_object_changed = _gl_on_scene_object_changed  # type: ignore[method-assign]


class Canvas2DGLWindowWidget(QWidget):
    """QWidget wrapper for a Canvas2D QOpenGLWindow backend."""

    view_changed = Signal(object)
    object_added = Signal(object)
    object_removed = Signal(object)
    object_changed = Signal(object, object)
    cursor_world_pos = Signal(float, float)
    selection_changed = Signal()
    active_selection_changed = Signal(object)
    modified_changed = Signal(bool)
    objects_moved = Signal(list)
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
        self._window.object_added.connect(self.object_added)
        self._window.object_removed.connect(self.object_removed)
        self._window.object_changed.connect(self.object_changed)
        self._window.cursor_world_pos.connect(self.cursor_world_pos)
        self._window.selection_changed.connect(self.selection_changed)
        self._window.active_selection_changed.connect(self.active_selection_changed)
        self._window.modified_changed.connect(self.modified_changed)
        self._window.objects_moved.connect(self.objects_moved)
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
