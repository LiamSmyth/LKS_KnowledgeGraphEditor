"""Deterministic lane layout for ordered node sequences."""
from __future__ import annotations

from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["LaneNodeLayoutAlgorithm2D"]


class LaneNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Place nodes into a single vertical or horizontal lane.

    Modes:
    - ``rect``: spacing includes node rect size (width/height).
    - ``point``: spacing ignores node size and uses fixed gap only.
    """

    def __init__(
        self,
        *,
        orientation: str = "vertical",
        lane_value: float = 0.0,
        start: float = 0.0,
        gap: float = 260.0,
        mode: str = "rect",
    ) -> None:
        self.orientation = orientation
        self.lane_value = float(lane_value)
        self.start = float(start)
        self.gap = float(gap)
        self.mode = mode

    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        del edges
        if not nodes:
            return {}

        axis = self.orientation.strip().lower()
        if axis not in {"vertical", "horizontal"}:
            raise ValueError(
                "orientation must be one of: vertical, horizontal")

        mode = self.mode.strip().lower()
        if mode not in {"rect", "point"}:
            raise ValueError("mode must be one of: rect, point")

        ordered = sorted(nodes, key=lambda n: (n.y, n.x, n.node_id))
        out: dict[str, tuple[float, float]] = {}
        cursor = float(self.start)

        for node in ordered:
            if axis == "vertical":
                x = float(self.lane_value)
                y = cursor
                out[node.node_id] = (x, y)
                cursor += float(self.gap)
                if mode == "rect":
                    cursor += max(0.0, float(node.height))
            else:
                x = cursor
                y = float(self.lane_value)
                out[node.node_id] = (x, y)
                cursor += float(self.gap)
                if mode == "rect":
                    cursor += max(0.0, float(node.width))

        return out
