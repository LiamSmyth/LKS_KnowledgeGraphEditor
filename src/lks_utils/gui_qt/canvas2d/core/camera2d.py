"""`Camera2D`: 2-D view state + animated navigation + bookmarks.

Extracted from ``Canvas2DWidget`` so it can be shared across multiple
views of the same scene and tested headlessly without a ``QWidget``.

Responsibilities:
* Stores the current ``ViewTransform`` (centre, zoom, rotation).
* Runs the ``go_to`` constant-time animation and the exponential
  smoothing pump used by wheel-zoom / drag-pan.
* Exposes ``reset_view``, ``reset_zoom``, ``fit_to_aabb``,
  ``fit_to_content``, ``zoom_in``, ``zoom_out``.
* Persists per-camera bookmarks (save / restore / delete).
* Carries the ``is_minimap: bool`` flag that ``Canvas2DRenderer``
  uses to route items to ``paint_minimap`` vs ``paint``.

``view_changed(ViewTransform)`` is emitted whenever the view changes.
``bookmarks_changed()`` is emitted after a save / restore / delete.
"""
from __future__ import annotations

import math
from math import hypot as math_hypot
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    pass


class Camera2D(QObject):
    """View state, animation, and bookmarks for a 2-D canvas viewport.

    Construct one for every independent view of a ``Scene2D``.  The
    ``Canvas2DWidget`` owns one and exposes all its methods and signals
    as forwards; companion widgets (minimap, thumbnail, second window)
    construct their own.

    Args:
        parent:     Qt parent object (optional).
        is_minimap: Pass ``True`` for minimap cameras; the renderer
                    routes to ``CanvasObject.paint_minimap`` when set.
    """

    #: Emitted every time the view changes (animation ticks, set_view,
    #: go_to instant, resize-driven fit, …).
    view_changed = Signal(object)  # ViewTransform

    #: Emitted after bookmark save / restore / delete.
    bookmarks_changed = Signal()

    # Animation constants (tune-able by subclasses / tests).
    GOTO_DURATION_MS: int = 220
    _MIN_ZOOM: float = 1.0 / 64.0
    _MAX_ZOOM: float = 256.0
    _ZOOM_STEP: float = 1.25
    _ROTATION_SNAP_DEG: float = 15.0

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        is_minimap: bool = False,
    ) -> None:
        super().__init__(parent)
        self._view: ViewTransform = ViewTransform()
        self.is_minimap: bool = is_minimap

        # go_to (constant-time animation).
        self._goto_timer: QTimer | None = None
        self._goto_start_view: ViewTransform | None = None
        self._goto_target_view: ViewTransform | None = None
        self._goto_duration_ms: int = 0
        self._goto_elapsed_ms: int = 0

        # Exponential-smoothing pump (wheel-zoom / drag-pan).
        self._anim_target_view: ViewTransform | None = None
        self._anim_timer: QTimer | None = None
        self._anim_alpha: float = 0.35

        # Per-camera named bookmarks.
        self._bookmarks: dict[str, ViewTransform] = {}
        self._stroke_locked: bool = False

    # ------------------------------------------------------------------ #
    # View access                                                          #
    # ------------------------------------------------------------------ #

    def view(self) -> ViewTransform:
        """Return the current view transform."""
        return self._view

    @property
    def is_locked(self) -> bool:
        """True when camera navigation is locked for an active stroke."""
        return self._stroke_locked

    def lock_for_stroke(self) -> None:
        """Lock camera navigation for stroke-stable view-space painting."""
        if self._stroke_locked:
            raise RuntimeError("Camera2D is already locked for stroke")
        self.cancel_view_animation()
        self._stroke_locked = True

    def unlock(self) -> None:
        """Release the stroke lock and allow navigation again."""
        if not self._stroke_locked:
            raise RuntimeError("Camera2D is not locked")
        self._stroke_locked = False

    def viewport_anchor_screen(self, widget_size: tuple[float, float]) -> tuple[int, int]:
        """Integer viewport anchor derived once per frame.

        The anchor is the rounded screen-space location of the unrotated
        world-space viewport origin at the current zoom.
        """
        w, h = widget_size
        cx, cy = self._view.center_world
        zoom = self._view.zoom
        return (
            int(round(cx * zoom - (w / 2.0))),
            int(round(cy * zoom - (h / 2.0))),
        )

    def set_zoom(self, zoom: float) -> None:
        """Set zoom while preserving center/rotation."""
        if self._stroke_locked:
            raise RuntimeError("Camera2D is locked for stroke")
        clamped = max(self._MIN_ZOOM, min(self._MAX_ZOOM, zoom))
        self.set_view(self._view.with_zoom(clamped))

    def set_view_center(self, center_world: tuple[float, float]) -> None:
        """Set view center while preserving zoom/rotation."""
        if self._stroke_locked:
            raise RuntimeError("Camera2D is locked for stroke")
        self.set_view(self._view.with_center(center_world))

    def set_rotation(self, rotation_radians: float) -> None:
        """Set view rotation while preserving center/zoom."""
        if self._stroke_locked:
            raise RuntimeError("Camera2D is locked for stroke")
        self.set_view(self._view.with_rotation(rotation_radians))

    def set_view(self, view: ViewTransform) -> None:
        """Immediately snap to *view* and emit ``view_changed``."""
        if view == self._view:
            return
        self._view = view
        self.view_changed.emit(view)

    # ------------------------------------------------------------------ #
    # Animated navigation                                                  #
    # ------------------------------------------------------------------ #

    def go_to(
        self,
        target: ViewTransform,
        *,
        animate: bool = True,
        duration_ms: int | None = None,
    ) -> None:
        """Navigate to *target*, optionally animated.

        Interrupts any in-flight animation so back-to-back calls
        re-target smoothly from the current interpolated view.
        """
        if self._stroke_locked:
            raise RuntimeError("Camera2D is locked for stroke")
        self.cancel_view_animation()
        if not animate:
            self.set_view(target)
            return
        duration = self.GOTO_DURATION_MS if duration_ms is None else duration_ms
        if duration <= 0 or target == self._view:
            self.set_view(target)
            return
        self._goto_start_view = self._view
        self._goto_target_view = target
        self._goto_duration_ms = duration
        self._goto_elapsed_ms = 0
        if self._goto_timer is None:
            self._goto_timer = QTimer(self)
            self._goto_timer.setInterval(16)
            self._goto_timer.timeout.connect(self._goto_tick)
        if not self._goto_timer.isActive():
            self._goto_timer.start()

    def cancel_view_animation(self) -> None:
        """Stop any in-flight animation and stay at the current view."""
        if self._goto_timer is not None and self._goto_timer.isActive():
            self._goto_timer.stop()
        self._goto_start_view = None
        self._goto_target_view = None
        self._goto_elapsed_ms = 0
        if self._anim_timer is not None and self._anim_timer.isActive():
            self._anim_timer.stop()
        self._anim_target_view = None

    def is_view_animating(self) -> bool:
        """True iff a go_to or smoothing-pump animation is running."""
        if self._goto_timer is not None and self._goto_timer.isActive():
            return True
        if self._anim_timer is not None and self._anim_timer.isActive():
            return True
        return False

    def fly_to(self, target: ViewTransform, duration_ms: int = 250) -> None:
        """Back-compat shim — delegates to :meth:`go_to`."""
        self.go_to(target, animate=True, duration_ms=duration_ms)

    def _goto_tick(self) -> None:
        target = self._goto_target_view
        start = self._goto_start_view
        if target is None or start is None or self._goto_timer is None:
            if self._goto_timer is not None:
                self._goto_timer.stop()
            return
        self._goto_elapsed_ms += 16
        t = min(1.0, self._goto_elapsed_ms / max(1, self._goto_duration_ms))
        self.set_view(start.lerp(target, _ease_in_out(t)))
        if t >= 1.0:
            self._goto_timer.stop()
            self._goto_start_view = None
            self._goto_target_view = None
            self._goto_elapsed_ms = 0

    # Exponential-smoothing pump (used by drag-pan / wheel-zoom).

    def begin_view_animation(self, target: ViewTransform, *, alpha: float = 0.35) -> None:
        """Push *target* as the smoothing-pump goal.

        ``alpha`` is the fraction of remaining distance consumed per ~16 ms
        tick. ``Canvas2DWidget`` calls this for wheel-zoom and drag-pan.
        """
        if self._stroke_locked:
            raise RuntimeError("Camera2D is locked for stroke")
        self._anim_target_view = target
        self._anim_alpha = alpha
        if self._anim_timer is None:
            self._anim_timer = QTimer(self)
            self._anim_timer.setInterval(16)
            self._anim_timer.timeout.connect(self._anim_tick)
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _anim_tick(self) -> None:
        target = self._anim_target_view
        if target is None or self._anim_timer is None:
            if self._anim_timer is not None:
                self._anim_timer.stop()
            return
        alpha = self._anim_alpha
        current = self._view
        # Detect "close enough" → snap to target and stop.
        zoom_delta = abs(target.zoom - current.zoom) / max(target.zoom, 1e-6)
        cx0, cy0 = current.center_world
        cx1, cy1 = target.center_world
        center_delta = math_hypot(cx1 - cx0, cy1 - cy0)
        rot_delta = abs(target.rotation_radians - current.rotation_radians)
        center_eps = 0.5 / max(current.zoom, 1e-6)
        if (
            zoom_delta < 1e-3
            and center_delta < center_eps
            and rot_delta < 1e-4
        ):
            self.set_view(target)
            self._anim_timer.stop()
            self._anim_target_view = None
            return
        self.set_view(current.lerp(target, alpha))

    # ------------------------------------------------------------------ #
    # Convenience navigation                                               #
    # ------------------------------------------------------------------ #

    def reset_view(self, *, animate: bool = False) -> None:
        """Reset to the default (identity) view."""
        self.go_to(ViewTransform(), animate=animate)

    def reset_zoom(self, *, animate: bool = False) -> None:
        """Reset zoom to 1:1 while keeping the current centre."""
        self.go_to(self._view.with_zoom(1.0), animate=animate)

    def zoom_in(self, *, animate: bool = True) -> None:
        """Step zoom in by ``_ZOOM_STEP``."""
        new_zoom = min(self._MAX_ZOOM, self._view.zoom * self._ZOOM_STEP)
        self.go_to(self._view.with_zoom(new_zoom), animate=animate)

    def zoom_out(self, *, animate: bool = True) -> None:
        """Step zoom out by ``_ZOOM_STEP``."""
        new_zoom = max(self._MIN_ZOOM, self._view.zoom / self._ZOOM_STEP)
        self.go_to(self._view.with_zoom(new_zoom), animate=animate)

    def fit_to_aabb(
        self,
        aabb: AABB,
        viewport_size_px: tuple[float, float],
        buffer_world_px: float = 0.0,
        *,
        animate: bool = False,
    ) -> None:
        """Fit the view so *aabb* fills the viewport."""
        vw, vh = viewport_size_px
        if vw <= 0 or vh <= 0:
            return
        cx = (aabb.x0 + aabb.x1) / 2.0
        cy = (aabb.y0 + aabb.y1) / 2.0
        w = max(1e-6, aabb.width + 2 * buffer_world_px)
        h = max(1e-6, aabb.height + 2 * buffer_world_px)
        zoom = min(vw / w, vh / h)
        zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, zoom))
        self.go_to(ViewTransform((cx, cy), zoom, 0.0), animate=animate)

    def fit_to_content(
        self,
        content_union: AABB | None,
        viewport_size_px: tuple[float, float],
        buffer_world_px: float = 64.0,
        *,
        animate: bool = False,
    ) -> None:
        """Fit the view to *content_union*; reset if None."""
        if content_union is None:
            self.reset_view(animate=animate)
            return
        self.fit_to_aabb(
            content_union,
            viewport_size_px,
            buffer_world_px=buffer_world_px,
            animate=animate,
        )

    # ------------------------------------------------------------------ #
    # Bookmarks                                                            #
    # ------------------------------------------------------------------ #

    def save_view(self, name: str) -> None:
        """Save the current view under *name*."""
        self._bookmarks[name] = self._view
        self.bookmarks_changed.emit()

    def restore_view(self, name: str, *, animate: bool = True) -> None:
        """Restore the bookmark named *name*; silently ignored if not found."""
        target = self._bookmarks.get(name)
        if target is not None:
            self.go_to(target, animate=animate)

    def delete_bookmark(self, name: str) -> None:
        """Remove bookmark *name*; silently ignored if not found."""
        if name in self._bookmarks:
            del self._bookmarks[name]
            self.bookmarks_changed.emit()

    def bookmarks(self) -> dict[str, ViewTransform]:
        """Return a snapshot of all saved bookmarks."""
        return dict(self._bookmarks)


def _ease_in_out(t: float) -> float:
    """Cubic ease-in-out for animated go_to."""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - pow(-2 * t + 2, 3) / 2


__all__ = ["Camera2D"]
