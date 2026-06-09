"""`Scene2D`: data model for a 2-D canvas — objects, overlays, dirty tracking.

Extracted from ``Canvas2DWidget`` so that multiple views (main canvas,
minimap, thumbnail panel, second window) can share *one scene* and
render through independent ``Camera2D`` + ``Canvas2DRenderer`` pairs
without any widget coupling.

``Scene2D`` is a ``QObject`` (carries signals) but has **no widget or
GL context dependency** — it can be constructed and mutated in headless
unit tests.

Signals:
    object_added(CanvasObject):        An object was added.
    object_removed(CanvasObject):      An object was removed.
    object_changed(CanvasObject, object): An object requested repaint; the
        second arg is the dirty world AABB or ``None``.
    dirty_changed():               The dirty tracker state changed.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.core.dirty_tracker import DirtyTracker
from lks_utils.gui_qt.canvas2d.core.selection_model import SelectionModel
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.spatial.aabb import AABB


class Scene2D(QObject):
    """Pure-data model for a 2-D canvas.

    Owns the ordered object list, overlay list, dirty tracker, and
    selection model. Multiple ``Canvas2DWidget`` / ``MinimapWidget``
    instances may share the same ``Scene2D`` by referencing it; edits
    in one view immediately reflect in all others via the shared signals.

    Args:
        parent: Qt parent (optional).
    """

    object_added = Signal(object)           # CanvasObject
    object_removed = Signal(object)         # CanvasObject
    object_changed = Signal(object, object)  # CanvasObject, AABB | None
    dirty_changed = Signal()
    #: Re-exported from the owned ``SelectionModel``; fires whenever
    #: the selection set changes.
    selection_changed = Signal()
    #: Re-exported from the owned ``SelectionModel``; fires whenever
    #: the active selected object changes.
    active_selection_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._objects: list[CanvasObject] = []
        self._overlays: list[ViewportOverlay] = []
        self._dirty = DirtyTracker()
        self._dirty.mark(None)  # first paint = full
        self._hud_providers: list[Callable[[], str]] = []
        self._selection = SelectionModel(self)
        self._selection.selection_changed.connect(self.selection_changed)
        self._selection.active_object_changed.connect(
            self.active_selection_changed)

    # ------------------------------------------------------------------ #
    # Object management                                                      #
    # ------------------------------------------------------------------ #

    def add_object(self, obj: CanvasObject, z_order: int | None = None) -> None:
        """Add *obj* to the scene, optionally overriding its ``z_order``."""
        if z_order is not None:
            obj.z_order = z_order
        obj._repaint_callback = self._on_object_repaint  # noqa: SLF001
        self._objects.append(obj)
        self._objects.sort(key=lambda it: it.z_order)
        self.object_added.emit(obj)
        self._dirty.mark(obj.bounds())
        self.dirty_changed.emit()

    def remove_object(self, obj: CanvasObject) -> None:
        """Remove *obj* from the scene."""
        if obj in self._objects:
            self._objects.remove(obj)
            obj._repaint_callback = None  # noqa: SLF001
            self._selection._on_object_removed(obj)  # noqa: SLF001
            self.object_removed.emit(obj)
            self._dirty.mark(obj.bounds())
            self.dirty_changed.emit()

    def objects(self) -> list[CanvasObject]:
        """Return a snapshot of the current object list (z-ordered)."""
        return list(self._objects)

    def move_object(self, obj: CanvasObject, z_order: int) -> None:
        """Change *obj*'s z-order and re-sort."""
        obj.z_order = z_order
        self._objects.sort(key=lambda it: it.z_order)
        self.object_changed.emit(obj, None)
        self.dirty_changed.emit()

    def bring_object_to_front(self, obj: CanvasObject) -> None:
        """Move *obj* above all other scene objects.

        The promoted object receives a z-order strictly greater than the
        current maximum z-order. This keeps ordering deterministic and
        guarantees it will be returned by :meth:`topmost_at` when bounds
        overlap.
        """
        if obj not in self._objects:
            return
        max_z = max((it.z_order for it in self._objects), default=0)
        self.move_object(obj, max_z + 1)

    # ------------------------------------------------------------------ #
    # Overlay management                                                   #
    # ------------------------------------------------------------------ #

    def add_overlay(self, overlay: ViewportOverlay) -> None:
        """Add a viewport overlay."""
        overlay._repaint_callback = self._on_object_repaint  # noqa: SLF001
        self._overlays.append(overlay)
        self._dirty.mark(None)
        self.dirty_changed.emit()

    def remove_overlay(self, overlay: ViewportOverlay) -> None:
        """Remove a viewport overlay."""
        if overlay in self._overlays:
            self._overlays.remove(overlay)
            overlay._repaint_callback = None  # noqa: SLF001
            self._dirty.mark(None)
            self.dirty_changed.emit()

    def overlays(self) -> list[ViewportOverlay]:
        """Return a snapshot of the overlay list."""
        return list(self._overlays)

    # ------------------------------------------------------------------ #
    # Dirty tracking                                                       #
    # ------------------------------------------------------------------ #

    def dirty_tracker(self) -> DirtyTracker:
        return self._dirty

    # ------------------------------------------------------------------ #
    # Selection                                                            #
    # ------------------------------------------------------------------ #

    def selection(self) -> SelectionModel:
        """Return the owned :class:`~lks_utils.gui_qt.canvas2d.core.selection_model.SelectionModel`."""
        return self._selection

    def select_object(self, obj: CanvasObject, *, additive: bool = False) -> None:
        """Select *obj*.

        Non-selectable objects (``obj.selectable == False``) are silently
        ignored.

        Args:
            obj:      The object to select.
            additive: When ``False`` (default) replaces the selection.
                      When ``True`` extends it.
        """
        self._selection.select(obj, additive=additive)

    def deselect_object(self, obj: CanvasObject) -> None:
        """Remove *obj* from the selection (no-op if not selected)."""
        self._selection.deselect(obj)

    def toggle_object_selection(self, obj: CanvasObject) -> None:
        """Toggle *obj* in the selection set."""
        self._selection.toggle(obj)

    def select_objects(
        self,
        objects: list[CanvasObject],
        *,
        additive: bool,
        preferred_active: CanvasObject | None = None,
    ) -> None:
        """Select multiple objects in one mutation.

        Args:
            objects: Candidate selectable objects.
            additive: When ``False`` replaces current selection first.
            preferred_active: Active selection object to preserve when still
                present after mutation.
        """
        self._selection.select_many(
            objects,
            additive=additive,
            preferred_active=preferred_active,
        )

    def deselect_objects(self, objects: list[CanvasObject]) -> None:
        """Deselect multiple objects in one mutation."""
        self._selection.deselect_many(objects)

    def select_range_to(self, obj: CanvasObject, *, additive: bool = False) -> None:
        """Select range from anchor to *obj* using scene object order."""
        ordered = [it for it in self._objects if getattr(it, "selectable", True)]
        self._selection.select_range(ordered, obj, additive=additive)

    def clear_selection(self) -> None:
        """Clear the selection (no-op if already empty)."""
        self._selection.clear()

    def selected_objects(self) -> list[CanvasObject]:
        """Return a snapshot of the current selection."""
        return self._selection.selected_objects()

    def active_selected_object(self) -> CanvasObject | None:
        """Return the active selected object (or None when selection is empty)."""
        return self._selection.active_object()

    # ------------------------------------------------------------------ #
    # Spatial queries                                                      #
    # ------------------------------------------------------------------ #

    def objects_in_aabb(self, world_aabb: AABB) -> list[CanvasObject]:
        """Return objects whose bounds intersect *world_aabb*.

        Objects with ``bounds() is None`` are always included (unbounded).
        """
        result = []
        for obj in self._objects:
            b = obj.bounds()
            if b is None or (
                b.x1 >= world_aabb.x0
                and b.x0 <= world_aabb.x1
                and b.y1 >= world_aabb.y0
                and b.y0 <= world_aabb.y1
            ):
                result.append(obj)
        return result

    def topmost_at(self, world_pt: tuple[float, float]) -> CanvasObject | None:
        """Return the topmost (highest z-order) object whose bounds contain *world_pt*.

        Objects with ``bounds() is None`` are excluded from this query.
        """
        for obj in reversed(self._objects):
            b = obj.bounds()
            if b is not None and b.contains_point(world_pt[0], world_pt[1]):
                return obj
        return None

    def union_bounds(self) -> AABB | None:
        """Return the union of all object bounds, or None if no bounded objects."""
        union: AABB | None = None
        for obj in self._objects:
            b = obj.bounds()
            if b is None:
                continue
            union = b if union is None else union.union(b)
        return union

    # ------------------------------------------------------------------ #
    # HUD providers                                                        #
    # ------------------------------------------------------------------ #

    def register_hud_provider(self, callback: Callable[[], str]) -> None:
        """Register a string-returning callback for verbose HUD overlays."""
        self._hud_providers.append(callback)

    def hud_strings(self) -> list[str]:
        """Return all registered HUD strings."""
        out: list[str] = []
        for cb in self._hud_providers:
            try:
                out.append(cb())
            except Exception:  # noqa: BLE001
                continue
        return out

    # ------------------------------------------------------------------ #
    # Internal repaint plumbing                                            #
    # ------------------------------------------------------------------ #

    def _on_object_repaint(self, obj: CanvasObject, region: AABB | None) -> None:
        self._dirty.mark(region)
        self.object_changed.emit(obj, region)
        self.dirty_changed.emit()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        """Serialise the scene to a plain dict.

        Only objects that implement ``to_dict()`` are persisted; others are
        skipped silently.
        """
        objects_data = []
        for obj in self._objects:
            object_to_dict = getattr(obj, "to_dict", None)
            if object_to_dict is not None:
                objects_data.append(object_to_dict())
        return {"objects": objects_data}

    def from_dict(self, data: dict, object_registry: dict | None = None) -> None:
        """Restore scene state from *data* (the output of :meth:`to_dict`).

*object_registry* maps ``"type"`` strings to factory callables.
Objects whose type is not found in the registry are skipped.
        """
        registry = object_registry or {}
        for object_data in data.get("objects", data.get("items", [])):
            type_key = object_data.get("type")
            factory = registry.get(type_key)
            if factory is None:
                continue
            obj = factory(object_data)
            self.add_object(obj)


__all__ = ["Scene2D"]
