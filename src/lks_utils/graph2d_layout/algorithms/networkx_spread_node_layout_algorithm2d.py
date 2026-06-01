"""NetworkX spring layout wrapped with a local rect-aware spread postprocess."""
from __future__ import annotations

import math

from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["NetworkXSpreadNodeLayoutAlgorithm2D"]


class NetworkXSpreadNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Compute spring positions with NetworkX, then spread rectangles locally.

    Existing/fixed nodes can be provided via ``fixed_positions`` and will be
    held in place during spring solving and spread passes.
    """

    def __init__(
        self,
        *,
        fixed_positions: dict[str, tuple[float, float]] | None = None,
        spring_iterations: int = 120,
        spring_k: float = 180.0,
        spring_seed: int = 42,
        spread_padding: float = 24.0,
        spread_iterations: int = 48,
        prevent_shape_overlaps: bool = True,
        shape_overlap_padding: float = 16.0,
        shape_overlap_iterations: int = 64,
    ) -> None:
        self.fixed_positions = dict(fixed_positions or {})
        self.spring_iterations = max(1, spring_iterations)
        self.spring_k = max(8.0, spring_k)
        self.spring_seed = spring_seed
        self.spread_padding = max(0.0, spread_padding)
        self.spread_iterations = max(1, spread_iterations)
        self.prevent_shape_overlaps = prevent_shape_overlaps
        self.shape_overlap_padding = max(0.0, shape_overlap_padding)
        self.shape_overlap_iterations = max(1, shape_overlap_iterations)

    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        if not nodes:
            return {}

        try:
            import networkx as nx
        except Exception:
            fallback = {node.node_id: (node.x, node.y) for node in nodes}
            return self._finalize_positions(
                nodes,
                fallback,
                prevent_shape_overlaps=self.prevent_shape_overlaps,
                overlap_padding=self.shape_overlap_padding,
                overlap_iterations=self.shape_overlap_iterations,
            )

        node_ids = [node.node_id for node in nodes]
        node_id_set = set(node_ids)
        graph = nx.Graph()
        graph.add_nodes_from(node_ids)
        for edge in edges:
            if edge.source_id not in node_id_set or edge.target_id not in node_id_set:
                continue
            if edge.source_id == edge.target_id:
                continue
            graph.add_edge(edge.source_id, edge.target_id)

        initial_positions = {node.node_id: (node.x, node.y) for node in nodes}
        initial_positions.update(
            {
                node_id: pos
                for node_id, pos in self.fixed_positions.items()
                if node_id in node_id_set
            }
        )
        fixed = [
            node_id for node_id in node_ids
            if node_id in self.fixed_positions
        ]

        raw_positions = nx.spring_layout(
            graph,
            pos=initial_positions,
            fixed=fixed if fixed else None,
            seed=self.spring_seed,
            iterations=self.spring_iterations,
            k=self.spring_k,
            scale=None,
        )
        positions = {
            node_id: (float(raw_positions[node_id][0]), float(
                raw_positions[node_id][1]))
            for node_id in node_ids
        }

        spread_positions = self._spread_positions(
            nodes,
            positions,
            fixed_ids=set(fixed),
            padding=self.spread_padding,
            iterations=self.spread_iterations,
        )
        if not self.prevent_shape_overlaps:
            return spread_positions
        return self._spread_positions(
            nodes,
            spread_positions,
            fixed_ids=set(fixed),
            padding=self.shape_overlap_padding,
            iterations=self.shape_overlap_iterations,
        )

    def _spread_positions(
        self,
        nodes: list[LayoutNode2D],
        positions: dict[str, tuple[float, float]],
        *,
        fixed_ids: set[str],
        padding: float,
        iterations: int,
    ) -> dict[str, tuple[float, float]]:
        node_ids = [node.node_id for node in nodes]
        sizes = {
            node.node_id: (max(1.0, node.width), max(1.0, node.height))
            for node in nodes
        }
        pos = {node_id: [positions[node_id][0], positions[node_id][1]]
               for node_id in node_ids}

        for _ in range(iterations):
            moved = False
            for index, node_id_a in enumerate(node_ids):
                ax, ay = pos[node_id_a]
                aw, ah = sizes[node_id_a]
                acx = ax + aw * 0.5
                acy = ay + ah * 0.5
                for node_id_b in node_ids[index + 1:]:
                    bx, by = pos[node_id_b]
                    bw, bh = sizes[node_id_b]
                    bcx = bx + bw * 0.5
                    bcy = by + bh * 0.5

                    delta_x = acx - bcx
                    delta_y = acy - bcy
                    required_x = (aw + bw) * 0.5 + padding
                    required_y = (ah + bh) * 0.5 + padding
                    overlap_x = required_x - abs(delta_x)
                    overlap_y = required_y - abs(delta_y)
                    if overlap_x <= 0.0 or overlap_y <= 0.0:
                        continue

                    if node_id_a in fixed_ids and node_id_b in fixed_ids:
                        continue

                    moved = True
                    if abs(delta_x) < 1e-6 and abs(delta_y) < 1e-6:
                        # Deterministic tie-breaker to avoid axis-locking stacks.
                        sign = 1.0 if node_id_a < node_id_b else -1.0
                        delta_x = sign
                        delta_y = 0.5 * sign

                    dist = math.hypot(delta_x, delta_y)
                    if dist < 1e-6:
                        continue
                    dir_x = delta_x / dist
                    dir_y = delta_y / dist

                    # Use the smaller penetration component to nudge apart while
                    # preserving spring orientation; iterating converges quickly.
                    shift = max(0.0, min(overlap_x, overlap_y))
                    if shift <= 0.0:
                        continue

                    if node_id_a in fixed_ids:
                        pos[node_id_b][0] -= dir_x * shift
                        pos[node_id_b][1] -= dir_y * shift
                    elif node_id_b in fixed_ids:
                        pos[node_id_a][0] += dir_x * shift
                        pos[node_id_a][1] += dir_y * shift
                    else:
                        half = shift * 0.5
                        pos[node_id_a][0] += dir_x * half
                        pos[node_id_a][1] += dir_y * half
                        pos[node_id_b][0] -= dir_x * half
                        pos[node_id_b][1] -= dir_y * half
            if not moved:
                break

        return {node_id: (xy[0], xy[1]) for node_id, xy in pos.items()}
