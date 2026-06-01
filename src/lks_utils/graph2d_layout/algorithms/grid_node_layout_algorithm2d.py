"""Grid layout algorithm — arranges nodes in a square grid."""
from __future__ import annotations

import math

from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["GridNodeLayoutAlgorithm2D"]


class GridNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Arrange nodes in a regular grid.

    **Tier**: points-only — sizes and edges are ignored.

    Nodes are placed in reading order (left-to-right, then top-to-bottom)
    in a roughly-square grid. The grid origin is ``(origin_x, origin_y)``
    and each cell is ``col_spacing`` wide and ``row_spacing`` tall.

    Args:
        col_spacing: Horizontal distance between node left-edges (px).
        row_spacing: Vertical distance between node top-edges (px).
        origin_x: X coordinate of the first node.
        origin_y: Y coordinate of the first node.
        cols: Fixed column count. If ``None`` uses ``ceil(sqrt(n))``.
    """

    def __init__(
        self,
        *,
        col_spacing: float = 220.0,
        row_spacing: float = 120.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        cols: int | None = None,
        prevent_shape_overlaps: bool = True,
        shape_overlap_padding: float = 8.0,
        shape_overlap_iterations: int = 64,
    ) -> None:
        self.col_spacing = col_spacing
        self.row_spacing = row_spacing
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.cols = cols
        self.prevent_shape_overlaps = prevent_shape_overlaps
        self.shape_overlap_padding = shape_overlap_padding
        self.shape_overlap_iterations = shape_overlap_iterations

    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        if not nodes:
            return {}

        num_cols = self.cols if self.cols is not None else max(1, int(math.ceil(math.sqrt(len(nodes)))))
        positions: dict[str, tuple[float, float]] = {}
        for idx, node in enumerate(nodes):
            row = idx // num_cols
            col = idx % num_cols
            x = self.origin_x + col * self.col_spacing
            y = self.origin_y + row * self.row_spacing
            positions[node.node_id] = (x, y)
        return self._finalize_positions(
            nodes,
            positions,
            prevent_shape_overlaps=self.prevent_shape_overlaps,
            overlap_padding=self.shape_overlap_padding,
            overlap_iterations=self.shape_overlap_iterations,
        )
