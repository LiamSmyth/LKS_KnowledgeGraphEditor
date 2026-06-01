"""Circular layout algorithm — arranges nodes on a circle."""
from __future__ import annotations

import math

from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["CircularNodeLayoutAlgorithm2D"]


class CircularNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Arrange nodes evenly on a circle.

    **Tier**: points-only — edges are ignored and sizes are used only to
    auto-compute a sensible default radius when ``radius`` is ``None``.

    Args:
        radius: Circle radius in world units. When ``None`` a radius is
            chosen automatically so nodes do not overlap: roughly
            ``(n * max_node_width) / (2 * pi)``.
        center_x: X coordinate of the circle centre.
        center_y: Y coordinate of the circle centre.
        start_angle_deg: Angle (degrees) for the first node, measured
            clockwise from the positive-x axis.
    """

    def __init__(
        self,
        *,
        radius: float | None = None,
        center_x: float = 0.0,
        center_y: float = 0.0,
        start_angle_deg: float = -90.0,
        prevent_shape_overlaps: bool = True,
        shape_overlap_padding: float = 8.0,
        shape_overlap_iterations: int = 64,
    ) -> None:
        self.radius = radius
        self.center_x = center_x
        self.center_y = center_y
        self.start_angle_deg = start_angle_deg
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

        if len(nodes) == 1:
            return {nodes[0].node_id: (self.center_x, self.center_y)}

        radius = self.radius
        if radius is None:
            max_w = max(n.width for n in nodes)
            radius = max(200.0, (len(nodes) * (max_w + 20.0)) / (2.0 * math.pi))

        angle_step = 2.0 * math.pi / len(nodes)
        start_rad = math.radians(self.start_angle_deg)

        positions: dict[str, tuple[float, float]] = {}
        for idx, node in enumerate(nodes):
            angle = start_rad + idx * angle_step
            x = self.center_x + radius * math.cos(angle)
            y = self.center_y + radius * math.sin(angle)
            positions[node.node_id] = (x, y)
        return self._finalize_positions(
            nodes,
            positions,
            prevent_shape_overlaps=self.prevent_shape_overlaps,
            overlap_padding=self.shape_overlap_padding,
            overlap_iterations=self.shape_overlap_iterations,
        )
