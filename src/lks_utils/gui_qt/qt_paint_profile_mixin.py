"""``QtPaintProfileMixin`` — generic ``paintEvent`` timing for any ``QWidget``.

Mixing this class into a ``QWidget`` subclass eliminates the per-widget
boilerplate of timing ``paintEvent``, patching ``renderer.last_frame_timings``,
and auto-injecting the ``Qt GL compose/flush`` stage for ``QOpenGLWidget``
descendants.

Usage — CPU widget
------------------
::

    class MyWidget(QtPaintProfileMixin, QWidget):
        def paintEvent(self, event: QPaintEvent) -> None:
            # Just render — no timing boilerplate needed
            painter = QPainter(self)
            self.renderer.paint(...)
            painter.end()

    profiler = QFrameProfilerWidget()
    profiler.attach(my_widget)   # reads my_widget.last_frame_timings

Usage — OpenGL widget
---------------------
::

    class MyGLWidget(QtPaintProfileMixin, QOpenGLWidget):
        def paintGL(self) -> None:
            ...  # GL rendering, sets renderer.last_frame_timings

        # No paintEvent override needed — the mixin provides one that
        # calls QOpenGLWidget.paintEvent → paintGL and records the
        # full outer scope including Qt's compose/flush pass.

How it works
------------
1. ``__init_subclass__`` wraps every ``paintEvent`` defined by a
   subclass at class-creation time.  The wrapper records ``t0`` before
   and ``t1`` after the original method runs.
2. For widgets without a ``paintEvent`` override (e.g. plain
   ``QOpenGLWidget`` subclasses), the mixin's own ``paintEvent``
   calls ``super().paintEvent(event)`` and provides the same timing.
3. After paint, ``_update_paint_timings`` reads
   ``self.renderer.last_frame_timings`` (if present), patches
   ``total_ms`` with the outer scope, and auto-injects a
   ``"Qt GL compose/flush"`` ``OverlayTiming`` when the gap between
   inner (``paintGL``) and outer (``paintEvent``) scopes is ≥ 0.05 ms.
4. For widgets without a renderer, a minimal synthetic ``FrameTimings``
   with only ``total_ms`` populated is stored and exposed via
   ``last_frame_timings``.
5. ``QFrameProfilerWidget.attach()`` reads ``canvas.last_frame_timings``
   directly — no manual ``push()`` calls required.

Thread safety
-------------
All timing code runs on the Qt GUI thread.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_renderer import FrameTimings


class QtPaintProfileMixin:
    """Mixin that auto-records ``FrameTimings`` on every ``paintEvent``.

    Attach to any ``QWidget`` or ``QOpenGLWidget`` subclass by placing it
    first in the MRO::

        class MyWidget(QtPaintProfileMixin, QWidget): ...
        class MyGLWidget(QtPaintProfileMixin, QOpenGLWidget): ...

    After each paint the timings are available via ``self.last_frame_timings``
    and are consumed automatically by ``QFrameProfilerWidget.attach()``.
    """

    # Per-instance backing store (set by _update_paint_timings).
    # Class-level sentinel avoids AttributeError on first access.
    _qt_prof_timings: FrameTimings | None = None

    # ------------------------------------------------------------------ #
    # Class-creation hook                                                  #
    # ------------------------------------------------------------------ #

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Wrap ``paintEvent`` defined by *cls* at class-creation time."""
        super().__init_subclass__(**kwargs)
        if "paintEvent" in cls.__dict__:
            original = cls.__dict__["paintEvent"]

            # type: ignore[override]
            def _wrapped(self, event, *, _orig: object = original) -> None:
                t0 = time.perf_counter()
                _orig(self, event)
                t1 = time.perf_counter()
                self._update_paint_timings(t0, t1)

            # Preserve the original name for tracebacks.
            _wrapped.__name__ = "paintEvent"
            _wrapped.__qualname__ = f"{cls.__qualname__}.paintEvent"
            cls.paintEvent = _wrapped  # type: ignore[method-assign]

    # ------------------------------------------------------------------ #
    # Fallback paintEvent (used when subclass has no override)            #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event: object) -> None:  # type: ignore[override]
        """Timed fallback ``paintEvent`` for widgets without their own override.

        Delegates to ``super().paintEvent(event)`` (e.g. ``QOpenGLWidget``
        which then calls ``paintGL``) and records the outer scope.
        """
        t0 = time.perf_counter()
        super().paintEvent(event)  # type: ignore[misc]
        t1 = time.perf_counter()
        self._update_paint_timings(t0, t1)

    # ------------------------------------------------------------------ #
    # Timing update                                                        #
    # ------------------------------------------------------------------ #

    def _update_paint_timings(self, t0: float, t1: float) -> None:
        """Patch ``renderer.last_frame_timings`` with the outer paint scope.

        Called automatically by the wrapped ``paintEvent``.  Do not call
        this method directly.

        Args:
            t0: ``time.perf_counter()`` value recorded *before* paint.
            t1: ``time.perf_counter()`` value recorded *after* paint.
        """
        outer_ms = (t1 - t0) * 1000.0

        renderer = getattr(self, "renderer", None)
        timings: FrameTimings | None = (
            getattr(renderer, "last_frame_timings",
                    None) if renderer is not None else None
        )

        if timings is not None:
            inner_ms = float(timings.total_ms)
            compose_ms = max(0.0, outer_ms - inner_ms)

            if compose_ms >= 0.05:
                # Only inject once per frame; guard against double-wrapping.
                existing_names = {o.name for o in timings.overlay_timings}
                if "Qt GL compose/flush" not in existing_names:
                    # Lazy import to avoid circular-import at module level.
                    from lks_utils.gui_qt.canvas2d.render.canvas_renderer import (
                        OverlayTiming,
                    )
                    timings.overlay_timings.append(
                        OverlayTiming(
                            name="Qt GL compose/flush",
                            z_order=2001,
                            duration_ms=compose_ms,
                        )
                    )

            timings.total_ms = outer_ms
            timings.frame_timestamp = t1
            timings.frame_start_timestamp = t0
            timings.frame_end_timestamp = t1
            self._qt_prof_timings = timings
        else:
            # Widget has no renderer — create a minimal synthetic record so
            # the profiler has something to display (total_ms only).
            from lks_utils.gui_qt.canvas2d.render.canvas_renderer import FrameTimings as _FT
            self._qt_prof_timings = _FT(
                frame_timestamp=t1,
                total_ms=outer_ms,
                background_ms=0.0,
                items_ms=0.0,
                frame_start_timestamp=t0,
                frame_end_timestamp=t1,
            )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    @property
    def last_frame_timings(self) -> FrameTimings | None:
        """Most recent ``FrameTimings`` snapshot, or ``None`` before first paint."""
        return self._qt_prof_timings


__all__ = ["QtPaintProfileMixin"]
