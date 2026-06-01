"""`Scene2D`: data model for a 2-D canvas — items, overlays, dirty tracking.

Extracted from ``Canvas2DWidget`` so that multiple views (main canvas,
minimap, thumbnail panel, second window) can share *one scene* and
render through independent ``Camera2D`` + ``Canvas2DRenderer`` pairs
without any widget coupling.

``Scene2D`` is a ``QObject`` (carries signals) but has **no widget or
GL context dependency** — it can be constructed and mutated in headless
unit tests.

Signals:
    item_added(CanvasItem):        An item was added.
    item_removed(CanvasItem):      An item was removed.
    item_changed(CanvasItem, object): An item requested repaint; the
        second arg is the dirty world AABB or ``None``.
    dirty_changed():               The dirty tracker state changed.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, Signal

from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.dirty_tracker import DirtyTracker
from lks_utils.gui_qt.canvas2d.selection_model import SelectionModel
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay
from lks_utils.spatial.aabb import AABB


class Scene2D(QObject):
    """Pure-data model for a 2-D canvas.

    Owns the ordered item list, overlay list, dirty tracker, and
    selection model. Multiple ``Canvas2DWidget`` / ``MinimapWidget``
    instances may share the same ``Scene2D`` by referencing it; edits
    in one view immediately reflect in all others via the shared signals.

    Args:
        parent: Qt parent (optional).
    """

    item_added = Signal(object)           # CanvasItem
    item_removed = Signal(object)         # CanvasItem
    item_changed = Signal(object, object)  # CanvasItem, AABB | None
    dirty_changed = Signal()
    #: Re-exported from the owned ``SelectionModel``; fires whenever
    #: the selection set changes.
    selection_changed = Signal()
    #: Re-exported from the owned ``SelectionModel``; fires whenever
    #: the active selected item changes.
    active_selection_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[CanvasItem] = []
        self._overlays: list[ViewportOverlay] = []
        self._dirty = DirtyTracker()
        self._dirty.mark(None)  # first paint = full
        self._hud_providers: list[Callable[[], str]] = []
        self._selection = SelectionModel(self)
        self._selection.selection_changed.connect(self.selection_changed)
        self._selection.active_item_changed.connect(
            self.active_selection_changed)

    # ------------------------------------------------------------------ #
    # Item management                                                      #
    # ------------------------------------------------------------------ #

    def add_item(self, item: CanvasItem, z_order: int | None = None) -> None:
        """Add *item* to the scene, optionally overriding its ``z_order``."""
        if z_order is not None:
            item.z_order = z_order
        item._repaint_callback = self._on_item_repaint  # noqa: SLF001
        self._items.append(item)
        self._items.sort(key=lambda it: it.z_order)
        self.item_added.emit(item)
        self._dirty.mark(item.bounds())
        self.dirty_changed.emit()

    def remove_item(self, item: CanvasItem) -> None:
        """Remove *item* from the scene."""
        if item in self._items:
            self._items.remove(item)
            item._repaint_callback = None  # noqa: SLF001
            self._selection._on_item_removed(item)  # noqa: SLF001
            self.item_removed.emit(item)
            self._dirty.mark(item.bounds())
            self.dirty_changed.emit()

    def items(self) -> list[CanvasItem]:
        """Return a snapshot of the current item list (z-ordered)."""
        return list(self._items)

    def move_item(self, item: CanvasItem, z_order: int) -> None:
        """Change *item*'s z-order and re-sort."""
        item.z_order = z_order
        self._items.sort(key=lambda it: it.z_order)
        self.item_changed.emit(item, None)
        self.dirty_changed.emit()

    def bring_item_to_front(self, item: CanvasItem) -> None:
        """Move *item* above all other scene items.

        The promoted item receives a z-order strictly greater than the
        current maximum z-order. This keeps ordering deterministic and
        guarantees it will be returned by :meth:`topmost_at` when bounds
        overlap.
        """
        if item not in self._items:
            return
        max_z = max((it.z_order for it in self._items), default=0)
        self.move_item(item, max_z + 1)

    # ------------------------------------------------------------------ #
    # Overlay management                                                   #
    # ------------------------------------------------------------------ #

    def add_overlay(self, overlay: ViewportOverlay) -> None:
        """Add a viewport overlay."""
        overlay._repaint_callback = self._on_item_repaint  # noqa: SLF001
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
        """Return the owned :class:`~lks_utils.gui_qt.canvas2d.selection_model.SelectionModel`."""
        return self._selection

    def select_item(self, item: CanvasItem, *, additive: bool = False) -> None:
        """Select *item*.

        Non-selectable items (``item.selectable == False``) are silently
        ignored.

        Args:
            item:     The item to select.
            additive: When ``False`` (default) replaces the selection.
                      When ``True`` extends it.
        """
        self._selection.select(item, additive=additive)

    def deselect_item(self, item: CanvasItem) -> None:
        """Remove *item* from the selection (no-op if not selected)."""
        self._selection.deselect(item)

    def toggle_item_selection(self, item: CanvasItem) -> None:
        """Toggle *item* in the selection set."""
        self._selection.toggle(item)

    def select_items(
        self,
        items: list[CanvasItem],
        *,
        additive: bool,
        preferred_active: CanvasItem | None = None,
    ) -> None:
        """Select multiple items in one mutation.

        Args:
            items: Candidate selectable items.
            additive: When ``False`` replaces current selection first.
            preferred_active: Active selection item to preserve when still
                present after mutation.
        """
        self._selection.select_many(
            items,
            additive=additive,
            preferred_active=preferred_active,
        )

    def deselect_items(self, items: list[CanvasItem]) -> None:
        """Deselect multiple items in one mutation."""
        self._selection.deselect_many(items)

    def select_range_to(self, item: CanvasItem, *, additive: bool = False) -> None:
        """Select range from anchor to *item* using scene item order."""
        ordered = [it for it in self._items if getattr(it, "selectable", True)]
        self._selection.select_range(ordered, item, additive=additive)

    def clear_selection(self) -> None:
        """Clear the selection (no-op if already empty)."""
        self._selection.clear()

    def selected_items(self) -> list[CanvasItem]:
        """Return a snapshot of the current selection."""
        return self._selection.selected_items()

    def active_selected_item(self) -> CanvasItem | None:
        """Return the active selected item (or None when selection is empty)."""
        return self._selection.active_item()

    # ------------------------------------------------------------------ #
    # Spatial queries                                                      #
    # ------------------------------------------------------------------ #

    def items_in_aabb(self, world_aabb: AABB) -> list[CanvasItem]:
        """Return items whose bounds intersect *world_aabb*.

        Items with ``bounds() is None`` are always included (unbounded).
        """
        result = []
        for item in self._items:
            b = item.bounds()
            if b is None or (
                b.x1 >= world_aabb.x0
                and b.x0 <= world_aabb.x1
                and b.y1 >= world_aabb.y0
                and b.y0 <= world_aabb.y1
            ):
                result.append(item)
        return result

    def topmost_at(self, world_pt: tuple[float, float]) -> CanvasItem | None:
        """Return the topmost (highest z-order) item whose bounds contain *world_pt*.

        Items with ``bounds() is None`` are excluded from this query.
        """
        for item in reversed(self._items):
            b = item.bounds()
            if b is not None and b.contains_point(world_pt[0], world_pt[1]):
                return item
        return None

    def union_bounds(self) -> AABB | None:
        """Return the union of all item bounds, or None if no bounded items."""
        union: AABB | None = None
        for item in self._items:
            b = item.bounds()
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

    def _on_item_repaint(self, item: CanvasItem, region: AABB | None) -> None:
        self._dirty.mark(region)
        self.item_changed.emit(item, region)
        self.dirty_changed.emit()

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        """Serialise the scene to a plain dict.

        Only items that implement ``to_dict()`` are persisted; others are
        skipped silently.
        """
        items_data = []
        for item in self._items:
            item_to_dict = getattr(item, "to_dict", None)
            if item_to_dict is not None:
                items_data.append(item_to_dict())
        return {"items": items_data}

    def from_dict(self, data: dict, item_registry: dict | None = None) -> None:
        """Restore scene state from *data* (the output of :meth:`to_dict`).

        *item_registry* maps ``"type"`` strings to factory callables.
        Items whose type is not found in the registry are skipped.
        """
        registry = item_registry or {}
        for item_data in data.get("items", []):
            type_key = item_data.get("type")
            factory = registry.get(type_key)
            if factory is None:
                continue
            item = factory(item_data)
            self.add_item(item)


__all__ = ["Scene2D"]
