"""Sugiyama (hierarchical/layered) layout algorithm."""
from __future__ import annotations

from collections import defaultdict

from lks_utils.graph2d_layout._graph_utils import (
    build_adjacency,
    build_components,
    topological_order_with_cycle_break,
)
from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["SugiyamaNodeLayoutAlgorithm2D"]

_DIRECTION = str  # "left_to_right" | "right_to_left" | "top_to_bottom" | "bottom_to_top"


class SugiyamaNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Layered graph layout (Sugiyama-style).

    **Tier**: graph-aware — uses both edge topology and node sizes.

    Assigns nodes to layers based on the topological order of a
    cycle-broken DAG, then applies a one-pass barycenter ordering to
    reduce edge crossings within each layer. Disconnected components are
    packed side-by-side with a configurable gap.

    Args:
        direction: Flow direction. One of ``"left_to_right"``,
            ``"right_to_left"``, ``"top_to_bottom"``, ``"bottom_to_top"``.
        layer_spacing: Distance between consecutive layers (px).
        node_spacing: Distance between sibling nodes within a layer (px).
        component_gap: Extra gap between disconnected components (px).
        origin_x: X origin of the entire layout.
        origin_y: Y origin of the entire layout.
    """

    def __init__(
        self,
        *,
        direction: _DIRECTION = "left_to_right",
        layer_spacing: float = 80.0,
        node_spacing: float = 50.0,
        component_gap: float = 100.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        prevent_shape_overlaps: bool = True,
        shape_overlap_padding: float = 8.0,
        shape_overlap_iterations: int = 64,
    ) -> None:
        self.direction = direction
        self.layer_spacing = layer_spacing
        self.node_spacing = node_spacing
        self.component_gap = component_gap
        self.origin_x = origin_x
        self.origin_y = origin_y
        self.prevent_shape_overlaps = prevent_shape_overlaps
        self.shape_overlap_padding = shape_overlap_padding
        self.shape_overlap_iterations = shape_overlap_iterations

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def compute(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> dict[str, tuple[float, float]]:
        if not nodes:
            return {}

        node_map = {n.node_id: n for n in nodes}
        node_ids = [n.node_id for n in nodes]
        components = build_components(node_ids, edges)

        horizontal = self.direction in ("left_to_right", "right_to_left")
        offset_x = self.origin_x
        offset_y = self.origin_y
        all_positions: dict[str, tuple[float, float]] = {}

        for component in components:
            comp_edges = [e for e in edges if e.source_id in set(component) and e.target_id in set(component)]
            local_pos, width, height = self._compute_component(
                component, comp_edges, node_map
            )
            for nid, (lx, ly) in local_pos.items():
                all_positions[nid] = (offset_x + lx, offset_y + ly)

            if horizontal:
                offset_y += height + self.component_gap
            else:
                offset_x += width + self.component_gap

        return self._finalize_positions(
            nodes,
            all_positions,
            prevent_shape_overlaps=self.prevent_shape_overlaps,
            overlap_padding=self.shape_overlap_padding,
            overlap_iterations=self.shape_overlap_iterations,
        )

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _compute_component(
        self,
        node_ids: list[str],
        edges: list[LayoutEdge2D],
        node_map: dict[str, LayoutNode2D],
    ) -> tuple[dict[str, tuple[float, float]], float, float]:
        """Layout one connected component.  Returns (positions, width, height)."""
        succ, pred = build_adjacency(node_ids, edges)
        order = topological_order_with_cycle_break(node_ids, succ, pred)
        order_index = {n: i for i, n in enumerate(order)}

        # Build forward-only DAG for layering.
        dag_succ: dict[str, set[str]] = {n: set() for n in node_ids}
        dag_pred: dict[str, set[str]] = {n: set() for n in node_ids}
        for edge in edges:
            if order_index.get(edge.source_id, -1) < order_index.get(edge.target_id, -1):
                dag_succ[edge.source_id].add(edge.target_id)
                dag_pred[edge.target_id].add(edge.source_id)

        layer_index: dict[str, int] = {n: 0 for n in node_ids}
        for n in order:
            for nxt in dag_succ[n]:
                layer_index[nxt] = max(layer_index[nxt], layer_index[n] + 1)

        layers: dict[int, list[str]] = defaultdict(list)
        for n in node_ids:
            layers[layer_index[n]].append(n)

        # Barycenter ordering to reduce crossings.
        rank_in_layer: dict[str, int] = {}
        max_layer = max(layers.keys()) if layers else 0
        for lid in range(max_layer + 1):
            layer_nodes = layers.get(lid, [])
            if lid == 0:
                ordered_layer = sorted(layer_nodes)
            else:
                def barycenter(n: str, _rank: dict[str, int] = rank_in_layer, _pred: dict[str, set[str]] = dag_pred) -> float:
                    prev = [_rank[p] for p in _pred[n] if p in _rank]
                    if prev:
                        return sum(prev) / len(prev)
                    return float(node_map[n].x)

                ordered_layer = sorted(layer_nodes, key=lambda n: (barycenter(n), n))
            layers[lid] = ordered_layer
            for idx, n in enumerate(ordered_layer):
                rank_in_layer[n] = idx

        # Compute step sizes using max node dimensions.
        max_w = max(node_map[n].width for n in node_ids)
        max_h = max(node_map[n].height for n in node_ids)
        x_step = max(float(self.layer_spacing), max_w + 40.0)
        y_step = max(float(self.node_spacing), max_h + 20.0)

        local_pos: dict[str, tuple[float, float]] = {}
        for lid, layer_nodes in layers.items():
            for idx, n in enumerate(layer_nodes):
                if self.direction == "right_to_left":
                    x = float(max_layer - lid) * x_step
                    y = float(idx) * y_step
                elif self.direction == "top_to_bottom":
                    x = float(idx) * y_step
                    y = float(lid) * x_step
                elif self.direction == "bottom_to_top":
                    x = float(idx) * y_step
                    y = float(max_layer - lid) * x_step
                else:  # left_to_right (default)
                    x = float(lid) * x_step
                    y = float(idx) * y_step
                local_pos[n] = (x, y)

        width = float(max_layer) * x_step + max_w
        max_rows = max((len(v) for v in layers.values()), default=1)
        height = float(max_rows - 1) * y_step + max_h
        return local_pos, width, height
