"""`SelectionModel`: ordered selection set for a `Canvas2D` scene.

Owned by `Scene2D`; forwarded by `Canvas2DWidget`.

Only objects with :attr:`~lks_utils.gui_qt.canvas2d.canvas_object.CanvasObject.selectable`
set to ``True`` (the default) can enter the selection. Attempts to
select a non-selectable object are silently ignored.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject


class SelectionModel(QObject):
    """Ordered set of selected `CanvasObject`s.

    Mutation methods emit :attr:`selection_changed` at most *once* per
    call, even if the underlying set was already in the requested state.

    Args:
        parent: Qt parent (optional).
    """

    #: Emitted exactly once after each mutation that changes the set.
    selection_changed = Signal()
    #: Emitted when the active selection object changes.
    active_object_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._selected: list[CanvasObject] = []
        self._active: CanvasObject | None = None
        self._anchor: CanvasObject | None = None

    def _emit_if_changed(
        self,
        *,
        previous_selected: list[CanvasObject],
        previous_active: CanvasObject | None,
    ) -> None:
        if previous_selected != self._selected:
            self.selection_changed.emit()
        if previous_active is not self._active:
            self.active_object_changed.emit(self._active)

    def _set_active(self, obj: CanvasObject | None) -> None:
        self._active = obj

    def _fallback_active(self) -> CanvasObject | None:
        if not self._selected:
            return None
        return self._selected[-1]

    # ------------------------------------------------------------------ #
    # Mutation                                                             #
    # ------------------------------------------------------------------ #

    def select(self, obj: CanvasObject, *, additive: bool = False) -> None:
        """Select *obj*.

        Args:
            obj:      The object to select.
            additive: When ``False`` (default) the existing selection is
                      replaced by ``{obj}``. When ``True`` the object is
                      added to the existing selection.

        Non-selectable objects (``obj.selectable == False``) are silently
        ignored; the selection is unchanged and the signal is **not**
        emitted.
        """
        if not getattr(obj, "selectable", True):
            return
        previous_selected = list(self._selected)
        previous_active = self._active
        if additive:
            if obj not in self._selected:
                self._selected.append(obj)
            self._set_active(obj)
        else:
            self._selected = [obj]
            self._set_active(obj)
        self._anchor = obj
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def toggle(self, obj: CanvasObject) -> None:
        """Toggle *obj* inside the current selection set.

        Selecting a non-selected object makes it active. Deselecting the
        active object falls back to the most recently selected remaining object.
        """
        if not getattr(obj, "selectable", True):
            return
        previous_selected = list(self._selected)
        previous_active = self._active
        if obj in self._selected:
            self._selected.remove(obj)
            if self._active is obj:
                self._set_active(self._fallback_active())
        else:
            self._selected.append(obj)
            self._set_active(obj)
        self._anchor = obj
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def select_range(
        self,
        ordered_objects: list[CanvasObject],
        target: CanvasObject,
        *,
        additive: bool,
    ) -> None:
        """Select a contiguous range from anchor to *target*.

        Args:
            ordered_objects: Stable ordered selectable objects used to evaluate
                range bounds.
            target: Range end object.
            additive: Whether to union the range into existing selection.
        """
        if not getattr(target, "selectable", True):
            return
        if target not in ordered_objects:
            return

        anchor = self._anchor if self._anchor in ordered_objects else None
        if anchor is None:
            anchor = target

        start = ordered_objects.index(anchor)
        end = ordered_objects.index(target)
        lo = min(start, end)
        hi = max(start, end)
        range_objects = ordered_objects[lo:hi + 1]

        previous_selected = list(self._selected)
        previous_active = self._active

        if not additive:
            self._selected = []

        for obj in range_objects:
            if obj not in self._selected:
                self._selected.append(obj)

        self._set_active(target)
        self._anchor = target
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    def deselect(self, obj: CanvasObject) -> None:
        """Remove *obj* from the selection.

        Silently ignored when *obj* is not selected.
        """
        previous_selected = list(self._selected)
        previous_active = self._active
        if obj in self._selected:
            self._selected.remove(obj)
            if self._active is obj:
                self._set_active(self._fallback_active())
            self._emit_if_changed(
                previous_selected=previous_selected,
                previous_active=previous_active,
            )

    def select_many(
        self,
        objects: list[CanvasObject],
        *,
        additive: bool,
        preferred_active: CanvasObject | None = None,
    ) -> None:
        """Select multiple objects in one mutation.

        Args:
            objects: Candidate objects to add/replace in selection order.
            additive: When ``False`` replace current selection first.
            preferred_active: Optional active object to retain/promote if it is
                still selected after the batch update.
        """
        previous_selected = list(self._selected)
        previous_active = self._active

        filtered: list[CanvasObject] = []
        for obj in objects:
            if not getattr(obj, "selectable", True):
                continue
            if obj in filtered:
                continue
            filtered.append(obj)

        if not additive:
            self._selected = []

        for obj in filtered:
            if obj not in self._selected:
                self._selected.append(obj)

        if self._selected:
            if preferred_active is not None and preferred_active in self._selected:
                self._set_active(preferred_active)
            elif filtered:
                # Bulk-select uses the first hit object as stable active target.
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

    def deselect_many(self, objects: list[CanvasObject]) -> None:
        """Deselect multiple objects in one mutation."""
        previous_selected = list(self._selected)
        previous_active = self._active

        for obj in objects:
            if obj not in self._selected:
                continue
            self._selected.remove(obj)
            if self._anchor is obj:
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

    def selected_objects(self) -> list[CanvasObject]:
        """Return a snapshot of the current selection (insertion order)."""
        return list(self._selected)

    def is_selected(self, obj: CanvasObject) -> bool:
        """Return ``True`` iff *obj* is currently selected."""
        return obj in self._selected

    def active_object(self) -> CanvasObject | None:
        """Return the currently active selection object, if any."""
        return self._active

    def clear_active(self) -> None:
        """Clear the active object without changing the selected set.

        Silently ignored (no signal) when there is no active object.
        """
        previous_selected = list(self._selected)
        previous_active = self._active
        self._set_active(None)
        self._emit_if_changed(
            previous_selected=previous_selected,
            previous_active=previous_active,
        )

    # ------------------------------------------------------------------ #
    # Internal — called by Scene2D                                        #
    # ------------------------------------------------------------------ #

    def _on_object_removed(self, obj: CanvasObject) -> None:
        """Drop *obj* from the selection when it is removed from the scene."""
        previous_selected = list(self._selected)
        previous_active = self._active
        if obj in self._selected:
            self._selected.remove(obj)
            if self._active is obj:
                self._set_active(self._fallback_active())
            if self._anchor is obj:
                self._anchor = None
            self._emit_if_changed(
                previous_selected=previous_selected,
                previous_active=previous_active,
            )


__all__ = ["SelectionModel"]
