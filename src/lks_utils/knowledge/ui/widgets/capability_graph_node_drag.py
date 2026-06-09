"""GraphNodeDragCapability — bespoke drag semantics for knowledge graph nodes."""
from __future__ import annotations

from collections.abc import Callable

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities.capability_drag import DragCapability

if False:  # TYPE_CHECKING-style import guard for host type hints only
    from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
        CapabilityHostObject,
    )


class GraphNodeDragCapability(DragCapability):
    """Drag with optional snap grid and linked multi-node sync callback."""

    capability_id = "graph_node_drag"
    schema_version = 1

    def __init__(
        self,
        *,
        snap: float | None = None,
        linked_sync: Callable[[tuple[float, float]], None] | None = None,
    ) -> None:
        super().__init__()
        self._snap = snap
        self._linked_sync = linked_sync

    def apply_delta(self, host, world_delta: tuple[float, float]) -> None:
        dx, dy = world_delta
        if self._snap is not None and self._snap > 0.0:
            dx = round(dx / self._snap) * self._snap
            dy = round(dy / self._snap) * self._snap
        adjusted = (dx, dy)
        super().apply_delta(host, adjusted)
        if self._linked_sync is not None:
            self._linked_sync(adjusted)


__all__ = ["GraphNodeDragCapability"]
