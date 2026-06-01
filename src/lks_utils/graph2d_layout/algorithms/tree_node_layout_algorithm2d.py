"""Tree/forest layout algorithm for nested directed structures."""
from __future__ import annotations

from collections import deque

from lks_utils.graph2d_layout._graph_utils import build_adjacency
from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["TreeNodeLayoutAlgorithm2D"]

_DIRECTION = str


class TreeNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Rooted tree / forest layout for nested graph structures.

    This algorithm targets tree-shaped or mostly-tree graphs. When the
    input is not a strict tree (multiple parents, extra cross-links, or
    cycles), it derives a stable spanning forest from the directed graph
    and lays out that forest while leaving non-tree edges available for
    rendering.

    Args:
        direction: One of ``"left_to_right"``, ``"right_to_left"``,
            ``"top_to_bottom"``, or ``"bottom_to_top"``.
        layer_spacing: Gap between parent and child layers.
        sibling_spacing: Gap between sibling subtrees on the cross axis.
        component_gap: Gap between forest roots / disconnected trees.
        origin_x: Layout origin x.
        origin_y: Layout origin y.
        prevent_shape_overlaps: Run final rect-aware overlap cleanup.
        shape_overlap_padding: Minimum rect gap for the cleanup pass.
        shape_overlap_iterations: Iteration budget for the cleanup pass.
    """

    def __init__(
        self,
        *,
        direction: _DIRECTION = "top_to_bottom",
        layer_spacing: float = 90.0,
        sibling_spacing: float = 50.0,
        component_gap: float = 120.0,
        origin_x: float = 0.0,
        origin_y: float = 0.0,
        prevent_shape_overlaps: bool = True,
        shape_overlap_padding: float = 8.0,
        shape_overlap_iterations: int = 64,
    ) -> None:
        self.direction = direction
        self.layer_spacing = layer_spacing
        self.sibling_spacing = sibling_spacing
        self.component_gap = component_gap
        self.origin_x = origin_x
        self.origin_y = origin_y
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

        node_map = {node.node_id: node for node in nodes}
        ordered_node_ids = self._sort_node_ids([node.node_id for node in nodes], node_map)
        valid_edges = [
            edge
            for edge in edges
            if edge.source_id in node_map and edge.target_id in node_map
        ]
        succ, pred = build_adjacency(ordered_node_ids, valid_edges)
        children, roots = self._build_spanning_forest(ordered_node_ids, succ, pred, node_map)

        horizontal = self.direction in ("left_to_right", "right_to_left")
        along_sizes = {
            node_id: (node_map[node_id].width if horizontal else node_map[node_id].height)
            for node_id in ordered_node_ids
        }
        cross_sizes = {
            node_id: (node_map[node_id].height if horizontal else node_map[node_id].width)
            for node_id in ordered_node_ids
        }
        along_step = max(max(along_sizes.values(), default=0.0) + self.layer_spacing, 1.0)

        span_cache: dict[str, float] = {}

        def subtree_span(node_id: str) -> float:
            cached = span_cache.get(node_id)
            if cached is not None:
                return cached
            child_ids = children[node_id]
            if not child_ids:
                span_cache[node_id] = cross_sizes[node_id]
                return span_cache[node_id]
            total_child_span = sum(subtree_span(child_id) for child_id in child_ids)
            total_child_span += self.sibling_spacing * max(0, len(child_ids) - 1)
            span_cache[node_id] = max(cross_sizes[node_id], total_child_span)
            return span_cache[node_id]

        positions: dict[str, tuple[float, float]] = {}

        def assign_subtree(node_id: str, depth: int, cross_center: float) -> None:
            node = node_map[node_id]
            along_pos = depth * along_step
            if horizontal:
                positions[node_id] = (along_pos, cross_center - node.height * 0.5)
            else:
                positions[node_id] = (cross_center - node.width * 0.5, along_pos)

            child_ids = children[node_id]
            if not child_ids:
                return

            total_child_span = sum(subtree_span(child_id) for child_id in child_ids)
            total_child_span += self.sibling_spacing * max(0, len(child_ids) - 1)
            current_cross = cross_center - total_child_span * 0.5
            for child_id in child_ids:
                child_span = subtree_span(child_id)
                child_center = current_cross + child_span * 0.5
                assign_subtree(child_id, depth + 1, child_center)
                current_cross += child_span + self.sibling_spacing

        current_cross = 0.0
        for root_id in roots:
            root_span = subtree_span(root_id)
            assign_subtree(root_id, 0, current_cross + root_span * 0.5)
            current_cross += root_span + self.component_gap

        mirrored = self._mirror_if_needed(positions, ordered_node_ids, node_map)
        offset_positions = {
            node_id: (x + self.origin_x, y + self.origin_y)
            for node_id, (x, y) in mirrored.items()
        }
        return self._finalize_positions(
            nodes,
            offset_positions,
            prevent_shape_overlaps=self.prevent_shape_overlaps,
            overlap_padding=self.shape_overlap_padding,
            overlap_iterations=self.shape_overlap_iterations,
        )

    def _build_spanning_forest(
        self,
        ordered_node_ids: list[str],
        succ: dict[str, set[str]],
        pred: dict[str, set[str]],
        node_map: dict[str, LayoutNode2D],
    ) -> tuple[dict[str, list[str]], list[str]]:
        children = {node_id: [] for node_id in ordered_node_ids}
        roots = [node_id for node_id in ordered_node_ids if not pred[node_id]]
        if not roots and ordered_node_ids:
            roots = [ordered_node_ids[0]]

        parent_of: dict[str, str | None] = {}
        visited: set[str] = set()

        def walk(root_id: str) -> None:
            queue: deque[str] = deque([root_id])
            parent_of.setdefault(root_id, None)
            while queue:
                node_id = queue.popleft()
                if node_id in visited:
                    continue
                visited.add(node_id)
                for child_id in self._sort_node_ids(list(succ[node_id]), node_map):
                    if child_id in visited or child_id in parent_of:
                        continue
                    parent_of[child_id] = node_id
                    children[node_id].append(child_id)
                    queue.append(child_id)

        ordered_roots = self._sort_node_ids(roots, node_map)
        for root_id in ordered_roots:
            walk(root_id)

        for node_id in ordered_node_ids:
            if node_id in visited:
                continue
            ordered_roots.append(node_id)
            walk(node_id)

        return children, ordered_roots

    def _mirror_if_needed(
        self,
        positions: dict[str, tuple[float, float]],
        ordered_node_ids: list[str],
        node_map: dict[str, LayoutNode2D],
    ) -> dict[str, tuple[float, float]]:
        if self.direction not in ("right_to_left", "bottom_to_top"):
            return positions

        if self.direction == "right_to_left":
            extent = max(
                positions[node_id][0] + node_map[node_id].width
                for node_id in ordered_node_ids
            )
            return {
                node_id: (extent - (positions[node_id][0] + node_map[node_id].width), positions[node_id][1])
                for node_id in ordered_node_ids
            }

        extent = max(
            positions[node_id][1] + node_map[node_id].height
            for node_id in ordered_node_ids
        )
        return {
            node_id: (positions[node_id][0], extent - (positions[node_id][1] + node_map[node_id].height))
            for node_id in ordered_node_ids
        }

    def _sort_node_ids(
        self,
        node_ids: list[str],
        node_map: dict[str, LayoutNode2D],
    ) -> list[str]:
        horizontal = self.direction in ("left_to_right", "right_to_left")
        if horizontal:
            return sorted(
                node_ids,
                key=lambda node_id: (node_map[node_id].y, node_map[node_id].x, node_id),
            )
        return sorted(
            node_ids,
            key=lambda node_id: (node_map[node_id].x, node_map[node_id].y, node_id),
        )