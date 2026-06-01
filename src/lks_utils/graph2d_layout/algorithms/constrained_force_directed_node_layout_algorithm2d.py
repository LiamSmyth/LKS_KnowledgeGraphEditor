"""Constrained force-directed layout with optional fixed nodes."""
from __future__ import annotations

import math

from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["ConstrainedForceDirectedNodeLayoutAlgorithm2D"]


class ConstrainedForceDirectedNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Run a simple force-directed optimization with optional pinned nodes.

    Modes:
    - ``rect``: uses width/height to compute repulsion threshold.
    - ``point``: uses a fixed point distance threshold.
    """

    def __init__(
        self,
        *,
        fixed_node_ids: set[str] | None = None,
        iterations: int = 120,
        step_size: float = 0.18,
        min_distance: float = 220.0,
        mode: str = "rect",
    ) -> None:
        self.fixed_node_ids = set(fixed_node_ids or set())
        self.iterations = max(1, int(iterations))
        self.step_size = float(step_size)
        self.min_distance = float(min_distance)
        self.mode = mode

    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        if not nodes:
            return {}

        mode = self.mode.strip().lower()
        if mode not in {"rect", "point"}:
            raise ValueError("mode must be one of: rect, point")

        node_map = {node.node_id: node for node in nodes}
        centers: dict[str, list[float]] = {}
        for node in nodes:
            centers[node.node_id] = [
                float(node.x) + float(node.width) * 0.5,
                float(node.y) + float(node.height) * 0.5,
            ]

        neighbors: dict[str, set[str]] = {
            node.node_id: set() for node in nodes}
        for edge in edges:
            if edge.source_id not in node_map or edge.target_id not in node_map:
                continue
            neighbors[edge.source_id].add(edge.target_id)
            neighbors[edge.target_id].add(edge.source_id)

        movable = [
            node_id for node_id in node_map if node_id not in self.fixed_node_ids]
        if not movable:
            return {node_id: (float(node.x), float(node.y)) for node_id, node in node_map.items()}

        for _ in range(self.iterations):
            deltas: dict[str, tuple[float, float]] = {}
            for node_id in movable:
                cx, cy = centers[node_id]
                ax = 0.0
                ay = 0.0

                linked = neighbors.get(node_id, set())
                if linked:
                    mean_x = sum(centers[nid][0]
                                 for nid in linked) / float(len(linked))
                    mean_y = sum(centers[nid][1]
                                 for nid in linked) / float(len(linked))
                    ax += (mean_x - cx) * 0.5
                    ay += (mean_y - cy) * 0.5

                for other_id, (ox, oy) in centers.items():
                    if other_id == node_id:
                        continue
                    dx = cx - ox
                    dy = cy - oy
                    dist_sq = dx * dx + dy * dy
                    if dist_sq <= 1e-6:
                        continue
                    dist = math.sqrt(dist_sq)
                    if mode == "rect":
                        node = node_map[node_id]
                        other = node_map[other_id]
                        threshold = max(
                            self.min_distance,
                            (float(node.width) + float(other.width)) * 0.5,
                            (float(node.height) + float(other.height)) * 0.5,
                        )
                    else:
                        threshold = self.min_distance
                    if dist >= threshold:
                        continue
                    strength = (threshold - dist) / max(1e-6, threshold)
                    ax += (dx / dist) * strength * 2.0
                    ay += (dy / dist) * strength * 2.0

                deltas[node_id] = (ax * self.step_size, ay * self.step_size)

            for node_id, (dx, dy) in deltas.items():
                centers[node_id][0] += dx
                centers[node_id][1] += dy

        out: dict[str, tuple[float, float]] = {}
        for node_id, node in node_map.items():
            cx, cy = centers[node_id]
            out[node_id] = (
                cx - float(node.width) * 0.5,
                cy - float(node.height) * 0.5,
            )
        return out
