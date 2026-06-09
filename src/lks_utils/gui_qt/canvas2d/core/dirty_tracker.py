"""`DirtyTracker`: accumulate per-object dirty regions across a frame.

`Canvas2D` calls :meth:`mark` from `CanvasObject.request_repaint` and
:meth:`take_union` at the start of `paintEvent` to compute the
combined dirty AABB to pass to items via `CanvasPaintContext`.
"""
from __future__ import annotations

from lks_utils.spatial.aabb import AABB


class DirtyTracker:
    """Accumulates dirty world-AABBs since the last `take_union`.

    A ``None`` mark means "full repaint requested". Once a full
    repaint is pending all subsequent partial marks collapse into it
    until :meth:`take_union` is called.
    """

    def __init__(self) -> None:
        self._regions: list[AABB] = []
        self._full: bool = False

    def mark(self, region: AABB | None) -> None:
        """Record a dirty region. ``None`` = full repaint."""
        if region is None:
            self._full = True
            self._regions.clear()
            return
        if self._full:
            return
        self._regions.append(region)

    def is_dirty(self) -> bool:
        return self._full or bool(self._regions)

    def take_union(self) -> AABB | None:
        """Return the union of accumulated regions and reset.

        Returns:
            ``None`` if a full repaint was requested or nothing is
            dirty (the caller should treat ``None`` as "no info — full
            repaint"). Otherwise the AABB union of all marked regions.
        """
        if self._full:
            self._full = False
            self._regions.clear()
            return None
        if not self._regions:
            return None
        result = self._regions[0]
        for r in self._regions[1:]:
            result = result.union(r)
        self._regions.clear()
        return result

    def clear(self) -> None:
        self._regions.clear()
        self._full = False


__all__ = ["DirtyTracker"]
