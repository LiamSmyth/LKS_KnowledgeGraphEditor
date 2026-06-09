"""Adapter: bridge Canvas2D objects to/from the graph2d_layout module."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["Canvas2DGraphLayoutAdapter"]


class Canvas2DGraphLayoutAdapter:
    """Non-invasive adapter for applying a layout to Canvas2D objects.

    This adapter works by duck-typing — it queries ``obj.bounds()``
    (an :class:`~lks_utils.gui_qt.canvas2d.core.aabb.AABB`) for the
    current position and size, and uses an optional *move_fn* callback
    to reposition objects without requiring any base-class changes.

    If no *move_fn* is supplied the adapter falls back to setting the
    ``x`` and ``y`` attributes directly on the object.

    Example::

        adapter = Canvas2DGraphLayoutAdapter(
            move_fn=lambda obj, x, y: obj.set_position(x, y)
        )
        nodes = adapter.extract_nodes(canvas_objects)
        result = pipeline.run(nodes, edges)
        adapter.apply_positions(canvas_objects, result.positions, scene=scene)

    Args:
        move_fn: Optional callable ``(obj, x, y) -> None`` used to
            reposition objects.  Receives the canvas object and new top-left
            corner coordinates.
        default_width: Fallback width (px) when ``obj.bounds()`` is not
            available.
        default_height: Fallback height (px) when ``obj.bounds()`` is
            not available.
    """

    def __init__(
        self,
        *,
        move_fn: Callable[[Any, float, float], None] | None = None,
        default_width: float = 180.0,
        default_height: float = 90.0,
    ) -> None:
        self.move_fn = move_fn
        self.default_width = default_width
        self.default_height = default_height

    # ------------------------------------------------------------------ #
    # Extraction                                                           #
    # ------------------------------------------------------------------ #

    def extract_nodes(
        self,
        objects: list[Any],
        *,
        id_fn: Callable[[Any], str] | None = None,
    ) -> list[LayoutNode2D]:
        """Build :class:`LayoutNode2D` list from Canvas2D objects.

        Args:
            objects: Iterable of canvas objects.
            id_fn: Optional callable ``(obj) -> str`` to derive
                a stable node id.  Defaults to ``str(id(obj))``.
        """
        nodes: list[LayoutNode2D] = []
        for obj in objects:
            node_id = id_fn(obj) if id_fn else str(id(obj))
            x, y, w, h = self._bounds_of(obj)
            nodes.append(LayoutNode2D(node_id=node_id, x=x, y=y, width=w, height=h))
        return nodes

    def extract_edges(
        self,
        object_pairs: list[tuple[Any, Any]],
        *,
        id_fn: Callable[[Any], str] | None = None,
    ) -> list[LayoutEdge2D]:
        """Build :class:`LayoutEdge2D` list from (source, target) pairs.

        Args:
            object_pairs: List of ``(source_object, target_object)`` tuples.
            id_fn: Optional id resolver (same convention as
                :meth:`extract_nodes`).
        """
        edges: list[LayoutEdge2D] = []
        for idx, (src, dst) in enumerate(object_pairs):
            src_id = id_fn(src) if id_fn else str(id(src))
            dst_id = id_fn(dst) if id_fn else str(id(dst))
            edges.append(LayoutEdge2D(edge_id=f"e{idx}", source_id=src_id, target_id=dst_id))
        return edges

    # ------------------------------------------------------------------ #
    # Application                                                          #
    # ------------------------------------------------------------------ #

    def apply_positions(
        self,
        objects: list[Any],
        positions: dict[str, tuple[float, float]],
        *,
        id_fn: Callable[[Any], str] | None = None,
        scene: Any | None = None,
    ) -> None:
        """Move canvas objects to the computed positions.

        Args:
            objects: Canvas objects to reposition.
            positions: Mapping from node id to ``(x, y)`` top-left.
            id_fn: Optional id resolver.
            scene: Optional :class:`~lks_utils.gui_qt.canvas2d.scene.Scene2D`
                instance.  When provided, ``scene.object_changed(obj, None)``
                is called after each move to trigger a repaint.
        """
        for obj in objects:
            node_id = id_fn(obj) if id_fn else str(id(obj))
            if node_id not in positions:
                continue
            x, y = positions[node_id]
            if self.move_fn is not None:
                self.move_fn(obj, x, y)
            else:
                if hasattr(obj, "x"):
                    obj.x = x
                if hasattr(obj, "y"):
                    obj.y = y
            if scene is not None and hasattr(scene, "object_changed"):
                scene.object_changed.emit(obj, None)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _bounds_of(self, obj: Any) -> tuple[float, float, float, float]:
        """Return ``(x, y, width, height)`` for a canvas object."""
        if hasattr(obj, "bounds"):
            try:
                b = obj.bounds()
                if b is not None:
                    return float(b.x0), float(b.y0), float(b.width), float(b.height)
            except Exception:
                pass
        # Fallback: read individual attributes.
        x = float(getattr(obj, "x", 0.0))
        y = float(getattr(obj, "y", 0.0))
        w = float(getattr(obj, "width", self.default_width))
        h = float(getattr(obj, "height", self.default_height))
        return x, y, w, h
