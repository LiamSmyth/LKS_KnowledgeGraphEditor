"""`CanvasObject`: ABC for things drawn into a `Canvas2D` viewport."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform


class CanvasObject(ABC):
    """Anything drawn into a `Canvas2D` scene.

    Subclass and override at minimum :meth:`paint`. Override
    :meth:`bounds`, :meth:`hit_test`, :meth:`handle_input`,
    :meth:`on_view_changed`, and :meth:`on_gpu_context_changed` as
    needed.

    Lifecycle:
        1. ``__init__`` — pure-Python construction; do NOT touch GPU.
        2. ``on_gpu_context_changed(gpu)`` — first time the canvas has
           a GL context (or whenever Qt rebuilds it). Allocate textures
           / shaders here. Re-callable across the object's lifetime.
        3. ``on_view_changed(transform)`` — once per view change before
           the next paint. Use to invalidate caches or swap LOD.
        4. ``paint(ctx)`` — called every frame the object is visible.
        5. ``handle_input(event) -> bool`` — return True to consume.

    The consume-or-fallthrough contract:
        ``Canvas2D`` walks objects top-down by z-order and calls
        ``handle_input`` on each that ``hit_test``s the cursor. The
        first object to return True consumes the event. Objects that
        return False let the canvas keep walking; if no object consumes,
        the canvas itself may handle the event (for built-in actions
        like CANVAS_PAN that are bound to the same physical button).
    """

    #: Higher = drawn later (on top). Equal-z objects render in
    #: insertion order.
    z_order: int = 0

    #: When ``False`` the object cannot be selected via
    #: :class:`~lks_utils.gui_qt.canvas2d.core.selection_model.SelectionModel`.
    #: Attempts to select it are silently ignored.
    selectable: bool = True

    #: When ``False`` the object is excluded from drag routing.
    draggable: bool = True

    #: Set to ``True`` when the object draws its own selection indicator
    #: (e.g. a highlighted border) so that the canvas-level
    #: :class:`~lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_selection.SelectionOverlay`
    #: skips drawing its external AABB outline around this object.
    manages_own_selection_highlight: bool = False

    # ------------------------------------------------------------------ #
    # Visual modulation                                                    #
    # ------------------------------------------------------------------ #

    def set_visual_modulation(
        self,
        *,
        opacity: float = 1.0,
        tint_rgba: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Apply generic visual modulation to this object.

        Args:
            opacity: Multiplicative object opacity in ``[0.0, 1.0]``.
            tint_rgba: Optional tint descriptor as normalized RGBA floats.
                Canvas-level renderers may choose how to apply this.
        """
        clamped = max(0.0, min(1.0, float(opacity)))
        old_bounds = self.bounds()
        old_opacity = getattr(self, "_visual_opacity", 1.0)
        old_tint = getattr(self, "_visual_tint_rgba", None)
        changed = old_opacity != clamped or old_tint != tint_rgba
        if not changed:
            return
        setattr(self, "_visual_opacity", clamped)
        setattr(self, "_visual_tint_rgba", tint_rgba)
        self.request_repaint(old_bounds)

    def clear_visual_modulation(self) -> None:
        """Reset visual modulation to passthrough defaults."""
        self.set_visual_modulation(opacity=1.0, tint_rgba=None)

    def visual_opacity(self) -> float:
        """Return multiplicative object opacity in ``[0.0, 1.0]``."""
        return float(getattr(self, "_visual_opacity", 1.0))

    def visual_tint_rgba(self) -> tuple[float, float, float, float] | None:
        """Return optional normalized RGBA tint tuple."""
        tint = getattr(self, "_visual_tint_rgba", None)
        return tint

    # ------------------------------------------------------------------ #
    # Lifecycle hooks (override as needed; defaults are no-ops)            #
    # ------------------------------------------------------------------ #

    def on_gpu_context_changed(self, gpu) -> None:  # noqa: ANN001
        """Called when the canvas's GPU context is created or rebuilt."""
        return None

    def on_view_changed(self, transform: ViewTransform) -> None:
        """Called once per view change before the next paint."""
        return None

    def hit_test(self, world_pt: tuple[float, float]) -> bool:
        """Default: True iff ``bounds()`` contains ``world_pt``."""
        b = self.bounds()
        if b is None:
            return False
        return b.contains_point(world_pt[0], world_pt[1])

    def is_visible(self, viewport_aabb: AABB) -> bool:
        """Return ``True`` when the object should be drawn this frame.

        The default implementation intersects :meth:`bounds` against the
        pre-computed world-space viewport AABB supplied by the renderer.
        Objects with ``bounds() is None`` (unbounded) always return ``True``.

        Override for more sophisticated LOD or always-hidden objects.

        Args:
            viewport_aabb: The world-space axis-aligned bounding box of
                           the visible viewport, pre-computed by the
                           renderer each frame.
        """
        b = self.bounds()
        if b is None:
            return True
        return viewport_aabb.intersects(b)

    def handle_input(self, event: CanvasInputEvent) -> bool:
        """Default: dispatch ``"wheel"`` phase to :meth:`handle_wheel`; ignore others."""
        if event.phase == "wheel" and event.delta is not None:
            delta_y = event.delta[1] / 120.0
            return self.handle_wheel(event.world_pos, delta_y)
        return False

    def handle_wheel(self, world_pos: tuple[float, float], delta_y: float) -> bool:
        """Handle a scroll-wheel event at *world_pos*.

        *delta_y* is normalised in scroll steps: positive = wheel up (scroll
        toward the top of a list / zoom in), negative = wheel down.

        Return ``True`` to consume the event and prevent canvas zoom/pan.
        The canvas calls this on the topmost hit-tested object before falling
        back to its own navigation handler, so innermost objects take priority.

        Default: return ``False`` (pass-through to canvas).
        """
        return False

    def tooltip_at(self, world_pt: tuple[float, float]) -> str | None:
        """Return hover tooltip text at ``world_pt``.

        The default implementation returns ``None`` (no tooltip).
        Subclasses can override to provide context-sensitive hover text.
        """
        return None

    def on_drag_begin(self, world_pos: tuple[float, float]) -> None:
        """Called when an object drag starts at ``world_pos``."""
        return None

    def on_drag(self, world_delta: tuple[float, float]) -> None:
        """Called with per-frame drag delta in world units."""
        return None

    def on_drag_end(self) -> None:
        """Called when an active object drag ends."""
        return None

    def bounds(self) -> AABB | None:
        """World-space AABB. ``None`` = unbounded / excluded from fit/minimap."""
        return None

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict | None:
        """Serialise this object to a plain dict for persistence.

        Return ``None`` (default) to opt-out — the object is silently
        skipped by :meth:`~lks_utils.gui_qt.canvas2d.core.scene2d.Scene2D.to_dict`
        and :meth:`~lks_utils.gui_qt.canvas2d.widgets.canvas_widget.Canvas2DWidget.to_document`.

        The returned dict **must** include a ``"type"`` key matching the
        name registered with
        :func:`~lks_utils.gui_qt.canvas2d.canvas_object_registry.register_canvas_object_type`
        so it can be reconstructed by
        :meth:`~lks_utils.gui_qt.canvas2d.widgets.canvas_widget.Canvas2DWidget.load_document`.
        """
        return None

    @classmethod
    def from_dict(cls, d: dict) -> CanvasObject:
        """Reconstruct an instance from a serialised dict.

        Subclasses that implement :meth:`to_dict` **must** override this.

        Raises:
            NotImplementedError: Always, for the base class.
        """
        raise NotImplementedError(
            f"{cls.__name__}.from_dict is not implemented."
        )

    def paint_minimap(self, ctx: CanvasPaintContext) -> None:
        """Optional: draw self into the minimap. Default = no-op."""
        return None

    # ------------------------------------------------------------------ #
    # Required                                                             #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def paint(self, ctx: CanvasPaintContext) -> None:
        """Render self into ``ctx``."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Repaint signalling                                                   #
    # ------------------------------------------------------------------ #

    def request_repaint(self, region: AABB | None = None) -> None:
        """Tell the host canvas this object needs to be repainted.

        ``region`` is a world-space AABB describing what changed; the
        canvas may use it to skip work for unchanged objects. Pass
        ``None`` to mean "the whole object bounds".

        ``Canvas2D.add_object`` wires up the repaint signal automatically.
        Objects added without a host (e.g. in unit tests) may set
        :attr:`_repaint_callback` directly.
        """
        cb = getattr(self, "_repaint_callback", None)
        if cb is not None:
            cb(self, region if region is not None else self.bounds())

    # Set by `Canvas2D.add_object`. Type: Callable[[CanvasObject, AABB|None], None]
    _repaint_callback: Callable[[CanvasObject, AABB | None], None] | None = None


__all__ = ["CanvasObject"]
