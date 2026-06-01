"""`MinimapWidget`: a small companion view showing the canvas at low LOD.

Shows the union of ``item.bounds()`` for every item in a `Scene2D` plus
an overlay rect tracking the current viewport camera. Click to recentre
the viewport; drag the viewport rect to scrub.

Items opt into minimap rendering by overriding
:meth:`CanvasItem.paint_minimap`. Items that don't override get a
default outline drawn from their ``bounds()``.

Construction
------------
New API (preferred)::

    minimap = MinimapWidget(scene, viewport_camera)

Back-compat factory (migrates at your own pace)::

    minimap = MinimapWidget.from_canvas(canvas_widget)

Design notes
------------
* The minimap owns its own ``Camera2D(is_minimap=True)`` that auto-fits
  to the scene's content union on every item change.
* ``Canvas2DRenderer`` paints items and overlays through the minimap camera.
  Overlays are rendered at minimap zoom via the CPU path; the minimap is
  intentionally small (≤240×180 px) so CPU rendering is not a bottleneck.
* The viewport-rect overlay is drawn on top by the widget itself.
* Coordinate model: the minimap fits the union of item bounds
  (plus a buffer) into its widget rect, preserving aspect ratio.
* Click → ``viewport_camera.go_to`` (180 ms); drag inside the
  viewport rect → ``viewport_camera.set_view`` (instantaneous).

GPU note
--------
The minimap is deliberately NOT a ``QOpenGLWidget``.  Putting two
``QOpenGLWidget`` instances in the same window (minimap + canvas) causes
ModernGL context conflicts: Qt's shared-context mechanism means a second
``moderngl.create_context()`` call can fail or wrap an already-owned context,
yielding a blank black widget.  The minimap is small enough that the CPU
rendering cost is negligible, and it avoids the shared-context hazard entirely.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
)
from PySide6.QtWidgets import QWidget

from lks_utils.gui_qt.canvas2d.camera2d import Camera2D
from lks_utils.gui_qt.canvas2d.canvas2d_renderer import Canvas2DRenderer, FrameTimings
from lks_utils.gui_qt.canvas2d.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.gui_qt.theme.palette import PALETTE
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_widget import Canvas2DWidget


class MinimapWidget(QWidget):
    """Companion overview widget for a `Scene2D`.

    Construct with a ``Scene2D`` and the ``Camera2D`` of the viewport you
    want to track.  Use :meth:`from_canvas` for the one-liner back-compat
    path.
    """

    _BUFFER_FRAC: float = 0.05  # 5% padding around content union
    _VIEWPORT_UPDATE_INTERVAL_MS: int = 16

    def __init__(
        self,
        scene: Scene2D,
        viewport_camera: Camera2D,
        *,
        viewport_size_px: tuple[float, float] = (800.0, 600.0),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._viewport_camera = viewport_camera
        self._viewport_size_px = viewport_size_px

        # Own minimap-space camera (is_minimap=True so Canvas2DRenderer
        # routes items through paint_minimap when overridden).
        self._minimap_camera = Camera2D(self, is_minimap=True)
        self._renderer = Canvas2DRenderer()

        self._dragging_viewport: bool = False
        self._drag_offset_world: tuple[float, float] = (0.0, 0.0)
        self._live_updates_enabled: bool = True

        self._cached_aabb: AABB | None = None
        self._world_cache_image: QImage | None = None
        self._world_cache_dirty: bool = True
        self._viewport_dirty: bool = True
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(self._VIEWPORT_UPDATE_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self.update)

        self.setMinimumSize(120, 90)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Visual styling.
        self._bg = QColor(PALETTE.get("panel_bg", "#1c1e26"))
        self._content_pen_color = QColor(
            PALETTE.get("text_secondary", "#888888"))
        self._viewport_pen_color = QColor(PALETTE.get("accent", "#5294ff"))
        self._viewport_fill_color = QColor(self._viewport_pen_color)
        self._viewport_fill_color.setAlpha(48)

        # Wire scene + viewport camera signals.
        scene.item_added.connect(self._on_scene_changed)
        scene.item_removed.connect(self._on_scene_changed)
        scene.item_changed.connect(self._on_scene_changed)
        viewport_camera.view_changed.connect(self._on_viewport_changed)

    # ------------------------------------------------------------------ #
    # Back-compat factory                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_canvas(
        cls,
        canvas: "Canvas2DWidget",
        parent: QWidget | None = None,
    ) -> "MinimapWidget":
        """Create a ``MinimapWidget`` from a ``Canvas2DWidget``.

        Zero-change migration path from the old
        ``MinimapWidget(canvas_widget)`` call.
        """
        return cls(
            canvas.scene,
            canvas.camera,
            viewport_size_px=(float(canvas.width()), float(canvas.height())),
            parent=parent,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_viewport_size_px(self, w: float, h: float) -> None:
        """Update the tracked viewport pixel size (used to draw the rect)."""
        self._viewport_size_px = (w, h)
        self._world_cache_dirty = True
        self._schedule_refresh(full=True)

    def set_live_updates_enabled(self, enabled: bool) -> None:
        """Enable/disable live viewport-driven minimap refreshes."""
        self._live_updates_enabled = bool(enabled)
        if self._live_updates_enabled:
            self._schedule_refresh(full=True)

    def last_frame_timings(self) -> FrameTimings | None:
        """Return the last CPU render timings for minimap world-layer paint."""
        return self._renderer.last_frame_timings

    # ------------------------------------------------------------------ #
    # Sizing                                                               #
    # ------------------------------------------------------------------ #

    def sizeHint(self) -> QSize:
        return QSize(220, 160)

    # ------------------------------------------------------------------ #
    # Signal handlers                                                      #
    # ------------------------------------------------------------------ #

    def _on_scene_changed(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
        self._world_cache_dirty = True
        self._schedule_refresh(full=True)

    def _on_viewport_changed(self, *args, **kwargs) -> None:  # noqa: ANN002,ANN003
        if not self._live_updates_enabled:
            return
        self._schedule_refresh(full=False)

    def _schedule_refresh(self, *, full: bool) -> None:
        if full:
            self._viewport_dirty = True
            self.update()
            return
        self._viewport_dirty = True
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    # ------------------------------------------------------------------ #
    # World <-> minimap coords                                             #
    # ------------------------------------------------------------------ #

    def _padded_aabb(self) -> AABB | None:
        """Scene content bounds plus the current viewport, padded."""
        content = self._scene.union_bounds()
        viewport = self._viewport_camera.view().viewport_aabb_world(
            self._viewport_size_px
        )
        if content is None:
            base = viewport
        else:
            base = content.union(viewport)
        size = max(base.width, base.height, 1.0)
        pad = size * self._BUFFER_FRAC
        return AABB(base.x0 - pad, base.y0 - pad, base.x1 + pad, base.y1 + pad)

    def _display_aabb(self) -> AABB | None:
        """Return a stable display AABB that avoids per-frame recenter churn."""
        viewport = self._viewport_camera.view().viewport_aabb_world(
            self._viewport_size_px
        )
        if self._cached_aabb is not None and self._cached_aabb.contains_aabb(viewport):
            return self._cached_aabb

        target = self._padded_aabb()
        if target is None:
            self._cached_aabb = None
            return None
        if self._cached_aabb is None:
            self._cached_aabb = target
            self._world_cache_dirty = True
            return self._cached_aabb

        expanded = self._cached_aabb.union(target)
        if expanded != self._cached_aabb:
            self._cached_aabb = expanded
            self._world_cache_dirty = True
        return self._cached_aabb

    def _minimap_view(self, aabb: AABB) -> ViewTransform:
        """Compute a ViewTransform that fits *aabb* into this widget."""
        w = float(self.width())
        h = float(self.height())
        zoom_x = w / max(aabb.width, 1e-9)
        zoom_y = h / max(aabb.height, 1e-9)
        zoom = min(zoom_x, zoom_y)
        cx = (aabb.x0 + aabb.x1) / 2.0
        cy = (aabb.y0 + aabb.y1) / 2.0
        return ViewTransform(center_world=(cx, cy), zoom=zoom)

    def _world_to_minimap(
        self,
        world_pt: tuple[float, float],
        aabb: AABB,
    ) -> tuple[float, float]:
        """Project a world point into minimap-widget coords (Y-down)."""
        wx, wy = world_pt
        w = float(self.width())
        h = float(self.height())
        zoom_x = w / max(aabb.width, 1e-9)
        zoom_y = h / max(aabb.height, 1e-9)
        zoom = min(zoom_x, zoom_y)
        proj_w = aabb.width * zoom
        proj_h = aabb.height * zoom
        ox = (w - proj_w) / 2.0
        oy = (h - proj_h) / 2.0
        sx = ox + (wx - aabb.x0) * zoom
        sy = oy + (aabb.y1 - wy) * zoom
        return (sx, sy)

    def _minimap_to_world(
        self,
        minimap_pt: tuple[float, float],
        aabb: AABB,
    ) -> tuple[float, float]:
        """Convert a minimap-widget point to world coords."""
        mx, my = minimap_pt
        w = float(self.width())
        h = float(self.height())
        zoom_x = w / max(aabb.width, 1e-9)
        zoom_y = h / max(aabb.height, 1e-9)
        zoom = min(zoom_x, zoom_y)
        proj_w = aabb.width * zoom
        proj_h = aabb.height * zoom
        ox = (w - proj_w) / 2.0
        oy = (h - proj_h) / 2.0
        wx = (mx - ox) / zoom + aabb.x0
        wy = aabb.y1 - (my - oy) / zoom
        return (wx, wy)

    # ------------------------------------------------------------------ #
    # Painting                                                             #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg)

        aabb = self._display_aabb()
        if aabb is None:
            painter.end()
            return

        self._paint_cached_world_layer(painter, aabb)

        painter.resetTransform()
        self._draw_viewport_rect(painter, aabb)
        self._draw_border(painter)
        self._viewport_dirty = False
        painter.end()

    def _paint_cached_world_layer(self, painter: QPainter, aabb: AABB) -> None:
        if self.width() <= 0 or self.height() <= 0:
            return
        if self._world_cache_dirty or self._world_cache_image is None:
            image = QImage(
                self.width(),
                self.height(),
                QImage.Format.Format_ARGB32_Premultiplied,
            )
            image.fill(self._bg)
            mini_painter = QPainter(image)
            mini_painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

            mini_view = self._minimap_view(aabb)
            self._minimap_camera.set_view(mini_view)
            self._renderer.paint(
                self._scene,
                self._minimap_camera,
                mini_painter,
                QRect(0, 0, self.width(), self.height()),
            )
            mini_painter.end()
            self._world_cache_image = image
            self._world_cache_dirty = False

        if self._world_cache_image is not None:
            painter.drawImage(0, 0, self._world_cache_image)

    def _draw_viewport_rect(self, painter: QPainter, aabb: AABB) -> None:
        """Draw the translucent viewport-position indicator rectangle."""
        viewport = self._viewport_camera.view().viewport_aabb_world(
            self._viewport_size_px
        )
        x0, y0 = self._world_to_minimap((viewport.x0, viewport.y1), aabb)
        x1, y1 = self._world_to_minimap((viewport.x1, viewport.y0), aabb)
        view_rect = QRectF(x0, y0, max(2.0, x1 - x0), max(2.0, y1 - y0))
        painter.setBrush(QBrush(self._viewport_fill_color))
        pen = QPen(self._viewport_pen_color)
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawRect(view_rect)

    def _draw_border(self, painter: QPainter) -> None:
        """Draw a 1 px border around the minimap widget edge."""
        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_pen = QPen(QColor(PALETTE.get("border", "#3a3d4d")))
        border_pen.setWidthF(1.0)
        painter.setPen(border_pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # ------------------------------------------------------------------ #
    # Mouse                                                                #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        aabb = self._display_aabb()
        if aabb is None:
            return
        click = (event.position().x(), event.position().y())
        wp = self._minimap_to_world(click, aabb)

        viewport = self._viewport_camera.view().viewport_aabb_world(
            self._viewport_size_px
        )
        if viewport.contains_point(wp[0], wp[1]):
            # Begin drag-scrub.
            self._dragging_viewport = True
            cx, cy = self._viewport_camera.view().center_world
            self._drag_offset_world = (wp[0] - cx, wp[1] - cy)
        else:
            # Click outside viewport rect → animated fly to clicked point.
            new_view = self._viewport_camera.view().with_center(wp)
            self._viewport_camera.go_to(
                new_view, animate=True, duration_ms=180)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._dragging_viewport:
            return super().mouseMoveEvent(event)
        aabb = self._display_aabb()
        if aabb is None:
            return
        pt = (event.position().x(), event.position().y())
        wp = self._minimap_to_world(pt, aabb)
        new_center = (
            wp[0] - self._drag_offset_world[0],
            wp[1] - self._drag_offset_world[1],
        )
        self._viewport_camera.set_view(
            self._viewport_camera.view().with_center(new_center)
        )
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging_viewport = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: ANN001
        super().resizeEvent(event)
        self._world_cache_dirty = True
        self._schedule_refresh(full=True)


__all__ = ["MinimapWidget"]
