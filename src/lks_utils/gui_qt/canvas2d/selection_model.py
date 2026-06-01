"""`SelectionModel`: ordered selection set for a `Canvas2D` scene.

Owned by `Scene2D`; forwarded by `Canvas2DWidget`.

Only items with :attr:`~lks_utils.gui_qt.canvas2d.canvas_item.CanvasItem.selectable`
set to ``True`` (the default) can enter the selection. Attempts to
select a non-selectable item are silently ignored.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem


class SelectionModel(QObject):
    """Ordered set of selected `CanvasItem`s.

    Mutation methods emit :attr:`selection_changed` at most *once* per
    call, even if the underlying set was already in the requested state.

    Args:
        parent: Qt parent (optional).
    """

    #: Emitted exactly once after each mutation that changes the set.
    selection_changed = Signal()
    #: Emitted when the active selection item changes.
    active_item_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected: list[CanvasItem] = []
        self._active: CanvasItem | None = None
        self._anchor: CanvasItem | None = None

    def _emit_if_changed(
        self,
        *,
        previous_selected: list[CanvasItem],
        previous_active: CanvasItem | None,
    ) -> None:
        if previous_selected != self._selected:
            self.selection_changed.emit()
        if previous_active is not self._active:
            self.active_item_changed.emit(self._active)

    def _set_active(self, item: CanvasItem | None) -> None:
        self._active = item

    def _fallback_active(self) -> CanvasItem | None:
        return None

    # ------------------------------------------------------------------ #
    # Mutation                                                             #
    # ------------------------------------------------------------------ #

    def select(self, item: CanvasItem, *, additive: bool = False) -> None:
        """Select *item*.

        Args:
            item:     The item to select.
            additive: When ``False`` (default) the existing selection is
                      replaced by ``{item}``. When ``True`` the item is
                      added to the existing selection.

        Non-selectable items (``item.selectable == False``) are silently
        ignored; the selection is unchanged and the signal is **not**
        emitted.
        """
        if not getattr(item, "selectable", True):
            return
        previous_selected = list(self._selected)
        previous_active = self._active
        if additive:
            if item not in self._selected:
                self._selected.append(item)
            self._set_active(item)
        else:
            self._selected = [item]
            self._set_active(item)
        self._anchor = item
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def toggle(self, item: CanvasItem) -> None:
        """Toggle *item* inside the current selection set.

        Selecting a non-selected item makes it active. Deselecting the
        active item falls back to the most recently selected remaining item.
        """
        if not getattr(item, "selectable", True):
            return
        previous_selected = list(self._selected)
        previous_active = self._active
        if item in self._selected:
            self._selected.remove(item)
            if self._active is item:
                self._set_active(self._fallback_active())
        else:
            self._selected.append(item)
            self._set_active(item)
        self._anchor = item
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def select_range(
        self,
        ordered_items: list[CanvasItem],
        target: CanvasItem,
        *,
        additive: bool,
    ) -> None:
        """Select a contiguous range from anchor to *target*.

        Args:
            ordered_items: Stable ordered selectable items used to evaluate
                range bounds.
            target: Range end item.
            additive: Whether to union the range into existing selection.
        """
        if not getattr(target, "selectable", True):
            return
        if target not in ordered_items:
            return

        anchor = self._anchor if self._anchor in ordered_items else None
        if anchor is None:
            anchor = target

        start = ordered_items.index(anchor)
        end = ordered_items.index(target)
        lo = min(start, end)
        hi = max(start, end)
        range_items = ordered_items[lo:hi + 1]

        previous_selected = list(self._selected)
        previous_active = self._active

        if not additive:
            self._selected = []

        for item in range_items:
            if item not in self._selected:
                self._selected.append(item)

        self._set_active(target)
        self._anchor = target
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def deselect(self, item: CanvasItem) -> None:
        """Remove *item* from the selection.

        Silently ignored when *item* is not selected.
        """
        previous_selected = list(self._selected)
        previous_active = self._active
        if item in self._selected:
            self._selected.remove(item)
            if self._active is item:
                self._set_active(self._fallback_active())
            self._emit_if_changed(
                previous_selected=previous_selected,
                previous_active=previous_active,
            )

    def select_many(
        self,
        items: list[CanvasItem],
        *,
        additive: bool,
        preferred_active: CanvasItem | None = None,
    ) -> None:
        """Select multiple items in one mutation.

        Args:
            items: Candidate items to add/replace in selection order.
            additive: When ``False`` replace current selection first.
            preferred_active: Optional active item to retain/promote if it is
                still selected after the batch update.
        """
        previous_selected = list(self._selected)
        previous_active = self._active

        filtered: list[CanvasItem] = []
        for item in items:
            if not getattr(item, "selectable", True):
                continue
            if item in filtered:
                continue
            filtered.append(item)

        if not additive:
            self._selected = []

        for item in filtered:
            if item not in self._selected:
                self._selected.append(item)

        if self._selected:
            if preferred_active is not None and preferred_active in self._selected:
                self._set_active(preferred_active)
            elif filtered:
                # Bulk-select uses the first hit item as stable active target.
                self._set_active(filtered[0])
            elif self._active not in self._selected:
                self._set_active(self._fallback_active())
        else:
            self._set_active(None)

        if filtered:
            self._anchor = filtered[-1]
        elif not self._selected:
            self._anchor = None

        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def deselect_many(self, items: list[CanvasItem]) -> None:
        """Deselect multiple items in one mutation."""
        previous_selected = list(self._selected)
        previous_active = self._active

        for item in items:
            if item not in self._selected:
                continue
            self._selected.remove(item)
            if self._anchor is item:
                self._anchor = None

        if self._active not in self._selected:
            self._set_active(self._fallback_active())
        if not self._selected:
            self._anchor = None

        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def clear(self) -> None:
        """Clear the selection.

        Silently ignored (no signal) when already empty.
        """
        previous_selected = list(self._selected)
        previous_active = self._active
        if self._selected:
            self._selected.clear()
            self._set_active(None)
            self._anchor = None
            self._emit_if_changed(
                previous_selected=previous_selected,
                previous_active=previous_active,
            )

    # ------------------------------------------------------------------ #
    # Query                                                                #
    # ------------------------------------------------------------------ #

    def selected_items(self) -> list[CanvasItem]:
        """Return a snapshot of the current selection (insertion order)."""
        return list(self._selected)

    def is_selected(self, item: CanvasItem) -> bool:
        """Return ``True`` iff *item* is currently selected."""
        return item in self._selected

    def active_item(self) -> CanvasItem | None:
        """Return the currently active selection item, if any."""
        return self._active

    # ------------------------------------------------------------------ #
    # Internal — called by Scene2D                                        #
    # ------------------------------------------------------------------ #

    def _on_item_removed(self, item: CanvasItem) -> None:
        """Drop *item* from the selection when it is removed from the scene."""
        previous_selected = list(self._selected)
        previous_active = self._active
        if item in self._selected:
            self._selected.remove(item)
            if self._active is item:
                self._set_active(self._fallback_active())
            if self._anchor is item:
                self._anchor = None
            self._emit_if_changed(
                previous_selected=previous_selected,
                previous_active=previous_active,
            )


__all__ = ["SelectionModel"]
