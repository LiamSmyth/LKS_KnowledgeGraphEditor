"""`Canvas2DRenderer`: stateless paint orchestration for a 2-D canvas.

Separates paint logic from the Qt widget shell (``Canvas2DWidget``).
The renderer's only job is to walk a ``Scene2D`` through a ``Camera2D``
into a ``QPainter`` — no widget state, no GPU context, no input routing.

The default ``Canvas2DRenderer`` uses ``QPainter`` (software-accelerated
via Qt's raster engine).  A GPU-backed subclass may override ``paint``
when raw GL access is needed.

Usage::

    renderer = Canvas2DRenderer()
    renderer.paint(scene, camera, painter, widget.rect())
    # or for headless export:
    image = renderer.paint_to_image(scene, camera, (800, 600))

Per-frame timing is always collected and exposed via
``renderer.last_frame_timings``.  Consumers such as ``PerfHudWidget``
or ``QFrameProfilerWidget`` may read it after each ``paint`` call.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QRect, QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QTransform

from lks_utils.gui_qt.canvas2d.camera2d import Camera2D
from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.dirty_tracker import DirtyTracker
from lks_utils.gui_qt.canvas2d.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE
from lks_utils.spatial.aabb import AABB


# ------------------------------------------------------------------ #
# Timing data                                                          #
# ------------------------------------------------------------------ #

@dataclass
class OverlayTiming:
    """Per-overlay frame timing."""

    name: str
    z_order: int
    duration_ms: float


@dataclass
class FrameTimings:
    """Lightweight per-frame timing snapshot produced by ``Canvas2DRenderer``.

    All durations are wall-clock milliseconds measured with
    ``time.perf_counter()``.  The overhead of collecting timings is
    ~200 ns per overlay/group — negligible compared to draw costs.

    Attributes:
        frame_timestamp:   ``time.perf_counter()`` at start of ``paint``.
        total_ms:          Whole ``paint`` call duration.
        background_ms:     ``fillRect`` background duration.
        items_ms:          All canvas items combined.
        overlay_timings:   Per-overlay name + duration, in paint order.
    """

    frame_timestamp: float
    total_ms: float
    background_ms: float
    items_ms: float
    frame_start_timestamp: float = 0.0
    frame_end_timestamp: float = 0.0
    #: Time for ``QPainter(widget)`` constructor in ``paintGL()`` —
    #: includes implicit GL state save / pipeline sync with ModernGL.
    #: Zero when rendering outside a QOpenGLWidget context.
    qpainter_init_ms: float = 0.0
    #: Time for ``painter.end()`` in ``paintGL()`` —
    #: includes Qt's accumulated GL command flush to the driver.
    #: Zero when rendering outside a QOpenGLWidget context.
    qpainter_flush_ms: float = 0.0
    overlay_timings: list[OverlayTiming] = field(default_factory=list)

    @property
    def overlays_ms(self) -> float:
        """Sum of all overlay durations."""
        return sum(o.duration_ms for o in self.overlay_timings)


class Canvas2DRenderer:
    """Stateless paint orchestrator.

    ``paint`` is designed to be called from ``Canvas2DWidget.paintEvent``
    or from ``paint_to_image`` for headless export.  No state is kept
    between calls — create one instance and reuse it freely.

    After each ``paint`` call, ``last_frame_timings`` holds a
    ``FrameTimings`` snapshot with per-overlay and aggregate costs.
    """

    def __init__(self) -> None:
        self._bg_color = QColor(PALETTE["canvas_bg"])
        self.last_frame_timings: FrameTimings | None = None

    # ------------------------------------------------------------------ #
    # Primary entry point                                                  #
    # ------------------------------------------------------------------ #

    def paint(
        self,
        scene: Scene2D,
        camera: Camera2D,
        painter: QPainter,
        viewport_rect_px: QRect | QRectF,
        *,
        hud_providers: tuple[Callable[[], str], ...] = (),
        paint_background: bool = True,
        excluded_overlays: set[int] | None = None,
    ) -> None:
        """Render *scene* through *camera* into *painter*.

        Paint order:
        1. Background fill.
        2. Backdrop overlays (``z_order < 0``) — e.g. dot grid.
        3. Items in z-order; optionally culled to the visible AABB.
        4. Foreground overlays (``z_order >= 0``).

        When ``camera.is_minimap`` is True and an item overrides
        :meth:`CanvasItem.paint_minimap`, ``paint_minimap`` is called
        instead of ``paint``.

        Args:
            scene:            The scene to render.
            camera:           Defines the current viewpoint.
            painter:          Active ``QPainter`` (caller owns begin/end).
            viewport_rect_px: Pixel rect of the viewport (usually
                              ``widget.rect()``).
            hud_providers:    Optional string callbacks for verbose HUD
                              overlays; forwarded to ``CanvasPaintContext``
                              via ``scene.hud_strings()``.
        """
        vr = viewport_rect_px
        vw = float(vr.width())
        vh = float(vr.height())
        view = camera.view()
        viewport_size = (vw, vh)
        viewport_aabb = view.viewport_aabb_world(viewport_size)

        # Consume the scene's dirty state to populate the context.
        dirty_region = scene.dirty_tracker().take_union()

        _t0 = time.perf_counter()
        _overlay_timings: list[OverlayTiming] = []

        _tbg0 = time.perf_counter()
        if paint_background:
            painter.fillRect(vr, self._bg_color)
        _bg_ms = (time.perf_counter() - _tbg0) * 1000.0

        ctx = CanvasPaintContext(
            painter=painter,
            view=view,
            viewport_size_px=viewport_size,
            viewport_aabb_world=viewport_aabb,
            dirty_region_world=dirty_region,
            device_pixel_ratio=float(
                max(painter.device().devicePixelRatioF(), 1.0)),
        )

        anchor = camera.viewport_anchor_screen((vw, vh))
        world_tf = _world_transform(view, vw, vh, anchor_screen=anchor)

        excluded = excluded_overlays or set()
        overlays = [ov for ov in scene.overlays() if id(ov) not in excluded]
        items = scene.items()
        is_minimap = camera.is_minimap
        if is_minimap:
            # Minimap is a world-space overview; viewport-locked chrome such as
            # HUDs, screen-space textures, and backdrops should not be repainted
            # there because they do not convey world content and can dominate
            # update cost during camera motion.
            overlays = [ov for ov in overlays if not ov.screen_space]

        # 1. Backdrop overlays (z_order < 0).
        bg_overlays = sorted(
            [ov for ov in overlays if ov.z_order < 0],
            key=lambda o: o.z_order,
        )
        for ov in bg_overlays:
            painter.save()
            if not ov.screen_space:
                painter.setTransform(world_tf)
            _tov = time.perf_counter()
            try:
                if isinstance(ov, ViewportOverlay):
                    ov.paint_cpu(ctx)
                else:
                    ov.paint(ctx)
            finally:
                painter.restore()
            _overlay_timings.append(OverlayTiming(
                name=type(ov).__name__,
                z_order=ov.z_order,
                duration_ms=(time.perf_counter() - _tov) * 1000.0,
            ))

        # 2. Items.
        _titems = time.perf_counter()
        for item in items:
            # Viewport culling: skip items that are entirely outside the
            # visible world AABB. Overlays are NEVER culled (handled below).
            if not item.is_visible(viewport_aabb):
                continue
            painter.save()
            painter.setTransform(world_tf)
            item_opacity = item.visual_opacity()
            if item_opacity < 0.999:
                painter.setOpacity(max(0.0, min(1.0, item_opacity)))
            try:
                if is_minimap and _has_minimap_override(item):
                    item.paint_minimap(ctx)
                else:
                    item.paint(ctx)
            finally:
                painter.restore()
        _items_ms = (time.perf_counter() - _titems) * 1000.0

        # 3. Foreground overlays (z_order >= 0).
        fg_overlays = sorted(
            [ov for ov in overlays if ov.z_order >= 0],
            key=lambda o: o.z_order,
        )
        for ov in fg_overlays:
            painter.save()
            if not ov.screen_space:
                painter.setTransform(world_tf)
            _tov = time.perf_counter()
            try:
                if isinstance(ov, ViewportOverlay):
                    ov.paint_cpu(ctx)
                else:
                    ov.paint(ctx)
            finally:
                painter.restore()
            _overlay_timings.append(OverlayTiming(
                name=type(ov).__name__,
                z_order=ov.z_order,
                duration_ms=(time.perf_counter() - _tov) * 1000.0,
            ))

        _t1 = time.perf_counter()
        self.last_frame_timings = FrameTimings(
            frame_timestamp=_t0,
            frame_start_timestamp=_t0,
            frame_end_timestamp=_t1,
            total_ms=(_t1 - _t0) * 1000.0,
            background_ms=_bg_ms,
            items_ms=_items_ms,
            overlay_timings=_overlay_timings,
        )

    # ------------------------------------------------------------------ #
    # Headless export                                                      #
    # ------------------------------------------------------------------ #

    def paint_to_image(
        self,
        scene: Scene2D,
        camera: Camera2D,
        size_px: tuple[int, int],
    ) -> QImage:
        """Render the scene into a new ``QImage`` without any widget.

        Args:
            scene:   The scene to render.
            camera:  Defines the viewpoint.
            size_px: ``(width, height)`` in pixels.

        Returns:
            A ``QImage`` in ``Format_ARGB32_Premultiplied`` format.
        """
        w, h = size_px
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        try:
            self.paint(scene, camera, painter, image.rect())
        finally:
            painter.end()
        return image


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _world_transform(
    view: ViewTransform,
    vw: float,
    vh: float,
    *,
    anchor_screen: tuple[int, int] | None = None,
) -> QTransform:
    """Qt affine transform that maps world coordinates to widget pixels."""
    cx, cy = view.center_world
    zoom = view.zoom
    rot = view.rotation_radians
    cos_r = math.cos(rot)
    sin_r = math.sin(rot)
    m11 = zoom * cos_r
    m12 = zoom * sin_r
    m21 = zoom * sin_r
    m22 = -zoom * cos_r
    if anchor_screen is not None and abs(rot) < 1e-8:
        # Integer-snapped translation for the common unrotated case.
        anchor_x, anchor_y = anchor_screen
        dx = float(-anchor_x)
        dy = float(anchor_y + int(round(vh)))
    else:
        dx = vw / 2.0 - (m11 * cx + m21 * cy)
        dy = vh / 2.0 - (m12 * cx + m22 * cy)
    return QTransform(m11, m12, m21, m22, dx, dy)


def _has_minimap_override(item: CanvasItem) -> bool:
    """Return True if *item*'s class overrides ``paint_minimap``."""
    return type(item).paint_minimap is not CanvasItem.paint_minimap


__all__ = ["Canvas2DRenderer"]
