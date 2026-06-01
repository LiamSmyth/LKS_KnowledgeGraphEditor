"""Abstract base class for 2D node layout algorithms."""
from __future__ import annotations

from abc import ABC, abstractmethod

from lks_utils.graph2d_layout.overlap_resolver2d import OverlapResolver2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["NodeLayoutAlgorithm2D"]


class NodeLayoutAlgorithm2D(ABC):
    """Base class for all 2D node layout algorithms.

    Each algorithm operates on a list of :class:`LayoutNode2D` and
    :class:`LayoutEdge2D` objects — pure-Python dataclasses with no Qt
    or canvas dependency — and returns a mapping of node IDs to
    ``(x, y)`` positions (top-left corner of each node's bounding box).

    Algorithms fall into three broad tiers based on what input they use:

    * **Points-only** (e.g. grid, circular): uses only ``node_id``
      ordering; ignores sizes and edges.
    * **Rect-aware** (e.g. overlap resolver): uses ``width`` / ``height``
      to avoid bounding-box collisions.
    * **Graph-aware** (e.g. Sugiyama, force-directed): uses both sizes
      and edge topology to produce topologically meaningful layouts.

    Implementations may choose which tier they operate at internally;
    the interface is the same regardless.
    """

    @abstractmethod
    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        """Compute layout positions for the given nodes and edges.

        Args:
            nodes: Nodes to lay out. Each has an ``x``, ``y`` hint and
                ``width`` / ``height`` for rect-aware algorithms.
            edges: Directed edges between nodes. Point-only algorithms
                may ignore this entirely.

        Returns:
            A dict mapping each ``node_id`` to its computed ``(x, y)``
            position (top-left corner).  All input node IDs must appear
            as keys in the result.
        """

    def _finalize_positions(
        self,
        nodes: list[LayoutNode2D],
        positions: dict[str, tuple[float, float]],
        *,
        prevent_shape_overlaps: bool = True,
        overlap_padding: float = 8.0,
        overlap_iterations: int = 64,
    ) -> dict[str, tuple[float, float]]:
        """Apply common post-processing to raw algorithm output.

        When ``prevent_shape_overlaps`` is enabled, this runs a
        rectangle-aware separation pass using node widths/heights.
        """
        if not prevent_shape_overlaps:
            return positions
        if not nodes:
            return positions
        if not any((n.width > 0.0 or n.height > 0.0) for n in nodes):
            return positions
        resolver = OverlapResolver2D(
            padding=overlap_padding,
            max_iterations=overlap_iterations,
        )
        return resolver.resolve(nodes, positions)
