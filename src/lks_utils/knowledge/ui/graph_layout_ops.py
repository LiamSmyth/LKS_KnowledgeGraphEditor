"""Graph placement and selection-layout helpers for the knowledge graph tab."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, pi, sin

from lks_utils.graph2d_layout.algorithms.circular_node_layout_algorithm2d import (
    CircularNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.grid_node_layout_algorithm2d import (
    GridNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.sugiyama_node_layout_algorithm2d import (
    SugiyamaNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.networkx_spread_node_layout_algorithm2d import (
    NetworkXSpreadNodeLayoutAlgorithm2D,
)

from lks_utils.graph2d_layout.algorithms.squarify_grid_node_layout_algorithm2d import (
    SquarifyGridNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D


def _minimum_circular_radius(
    *,
    ordered_ids: list[str],
    sizes_by_id: dict[str, tuple[float, float]],
    gap: float,
) -> float:
    """Return the minimum radius needed to prevent overlap on a circle.

    Computes a conservative lower bound by checking every pair of nodes placed
    on evenly spaced angular slots and ensuring the chord distance can fit the
    sum of half-diagonals plus gap.
    """
    count = len(ordered_ids)
    if count <= 1:
        return 0.0

    half_diagonals = [
        hypot(sizes_by_id[nid][0], sizes_by_id[nid][1]) * 0.5
        for nid in ordered_ids
    ]
    radius = 0.0
    for i in range(count):
        for j in range(i + 1, count):
            step = min(j - i, count - (j - i))
            angle = pi * step / count
            sin_term = max(1e-6, sin(angle))
            required_center_distance = half_diagonals[i] + \
                half_diagonals[j] + gap
            radius = max(radius, required_center_distance / (2.0 * sin_term))
    return radius


@dataclass(frozen=True, slots=True)
class LayoutRequest:
    """Selection-scoped graph layout request."""

    node_ids: tuple[str, ...]
    algorithm_key: str


def compact_pack_positions(
    *,
    anchor_x: float,
    anchor_y: float,
    count: int,
    occupied_cells: set[tuple[int, int]],
    spacing_x: float = 160.0,
    spacing_y: float = 100.0,
) -> list[tuple[float, float]]:
    """Return compact, non-overlapping positions around an anchor.

    Cells are selected in increasing ring distance from the anchor cell.
    """
    if count <= 0:
        return []

    positions: list[tuple[float, float]] = []
    ax = int(round(anchor_x / spacing_x))
    ay = int(round(anchor_y / spacing_y))
    radius = 0
    used = set(occupied_cells)

    while len(positions) < count:
        for gx in range(ax - radius, ax + radius + 1):
            for gy in range(ay - radius, ay + radius + 1):
                if max(abs(gx - ax), abs(gy - ay)) != radius:
                    continue
                cell = (gx, gy)
                if cell in used:
                    continue
                used.add(cell)
                positions.append((gx * spacing_x, gy * spacing_y))
                if len(positions) >= count:
                    return positions
        radius += 1

    return positions


def layout_positions(
    *,
    algorithm_key: str,
    current_positions: dict[str, tuple[float, float]],
    node_sizes: dict[str, tuple[float, float]] | None = None,
    edge_pairs: list[tuple[str, str]] | None = None,
    gap: float = 20.0,
    target_aspect: float | None = 1.0,
) -> dict[str, tuple[float, float]]:
    """Return new positions for selected nodes.

    Parameters
    ----------
    algorithm_key:
        One of ``"line"``, ``"grid"``, ``"radial"``, ``"sugiyama"``, or
        ``"networkx_spread"``.
    current_positions:
        Current top-left (x, y) for each node, keyed by node id.
    node_sizes:
        Width and height for each node id.  When supplied the algorithms use
        the actual node dimensions so that output positions have no overlaps.
        Nodes missing from this dict fall back to (140.0, 80.0).
    gap:
        Minimum clear space (world units) between adjacent nodes.
    target_aspect:
        Target width/height ratio for the grid cluster (``"grid"`` algorithm
        only).  ``1.0`` = square, ``None`` = no optimisation (uses
        ``ceil(sqrt(n))`` columns).  Ignored by algorithms other than ``"grid"``.
    """
    _DEFAULT_W = 140.0
    _DEFAULT_H = 80.0

    def _size(nid: str) -> tuple[float, float]:
        if node_sizes:
            return node_sizes.get(nid, (_DEFAULT_W, _DEFAULT_H))
        return (_DEFAULT_W, _DEFAULT_H)

    if not current_positions:
        return {}

    ordered_ids = sorted(current_positions.keys())
    xs = [p[0] for p in current_positions.values()]
    ys = [p[1] for p in current_positions.values()]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    if algorithm_key == "line":
        max_w = max(_size(nid)[0] for nid in ordered_ids)
        max_h = max(_size(nid)[1] for nid in ordered_ids)
        col_spacing = max_w + gap
        row_spacing = max_h + gap
        total_w = max_w + (len(ordered_ids) - 1) * col_spacing
        origin_x = cx - total_w * 0.5
        origin_y = cy - max_h * 0.5

        line_nodes: list[LayoutNode2D] = [
            LayoutNode2D(
                node_id=nid,
                x=current_positions[nid][0],
                y=current_positions[nid][1],
                width=_size(nid)[0],
                height=_size(nid)[1],
            )
            for nid in ordered_ids
        ]
        line_alg = GridNodeLayoutAlgorithm2D(
            col_spacing=col_spacing,
            row_spacing=row_spacing,
            origin_x=origin_x,
            origin_y=origin_y,
            cols=len(ordered_ids),
            prevent_shape_overlaps=True,
            shape_overlap_padding=gap,
        )
        line_result = line_alg.compute(line_nodes, [])
        # Keep one horizontal baseline while preserving x positions from the
        # centralized grid algorithm.
        for nid in ordered_ids:
            _, h = _size(nid)
            x, _ = line_result[nid]
            line_result[nid] = (x, cy - h * 0.5)
        return line_result

    if algorithm_key == "grid":
        alg_nodes: list[LayoutNode2D] = [
            LayoutNode2D(
                node_id=nid,
                x=current_positions[nid][0],
                y=current_positions[nid][1],
                width=_size(nid)[0],
                height=_size(nid)[1],
            )
            for nid in ordered_ids
        ]
        grid_alg = SquarifyGridNodeLayoutAlgorithm2D(
            gap=gap,
            target_aspect=target_aspect,
            center_x=cx,
            center_y=cy,
        )
        return grid_alg.compute(alg_nodes, [])

    if algorithm_key == "radial":
        sizes_by_id = {nid: _size(nid) for nid in ordered_ids}
        min_radius = _minimum_circular_radius(
            ordered_ids=ordered_ids,
            sizes_by_id=sizes_by_id,
            gap=gap,
        )
        radial_nodes: list[LayoutNode2D] = [
            LayoutNode2D(
                node_id=nid,
                x=current_positions[nid][0],
                y=current_positions[nid][1],
                width=sizes_by_id[nid][0],
                height=sizes_by_id[nid][1],
            )
            for nid in ordered_ids
        ]
        radial_alg = CircularNodeLayoutAlgorithm2D(
            radius=max(200.0, min_radius),
            center_x=cx,
            center_y=cy,
            prevent_shape_overlaps=True,
            shape_overlap_padding=gap,
        )
        radial_centers = radial_alg.compute(radial_nodes, [])
        radial_result: dict[str, tuple[float, float]] = {}
        for nid in ordered_ids:
            w, h = sizes_by_id[nid]
            center_x, center_y = radial_centers[nid]
            radial_result[nid] = (center_x - w * 0.5, center_y - h * 0.5)
        return radial_result

    if algorithm_key == "sugiyama":
        sugiyama_nodes: list[LayoutNode2D] = [
            LayoutNode2D(
                node_id=nid,
                x=current_positions[nid][0],
                y=current_positions[nid][1],
                width=_size(nid)[0],
                height=_size(nid)[1],
            )
            for nid in ordered_ids
        ]
        id_set = set(ordered_ids)
        sugiyama_edges: list[LayoutEdge2D] = []
        if edge_pairs:
            for idx, (source_id, target_id) in enumerate(edge_pairs):
                if source_id not in id_set or target_id not in id_set:
                    continue
                if source_id == target_id:
                    continue
                sugiyama_edges.append(
                    LayoutEdge2D(
                        edge_id=f"sel_edge_{idx}",
                        source_id=source_id,
                        target_id=target_id,
                    )
                )
        max_h = max(_size(nid)[1] for nid in ordered_ids)
        max_w = max(_size(nid)[0] for nid in ordered_ids)
        sugiyama_alg = SugiyamaNodeLayoutAlgorithm2D(
            direction="left_to_right",
            layer_spacing=max(gap * 2.0, max_w + gap),
            node_spacing=max(gap * 2.0, max_h + gap),
            origin_x=0.0,
            origin_y=0.0,
            prevent_shape_overlaps=True,
            shape_overlap_padding=gap,
        )
        raw_positions = sugiyama_alg.compute(sugiyama_nodes, sugiyama_edges)
        if not raw_positions:
            return {}
        center_x = sum(pos[0]
                       for pos in raw_positions.values()) / len(raw_positions)
        center_y = sum(pos[1]
                       for pos in raw_positions.values()) / len(raw_positions)
        dx = cx - center_x
        dy = cy - center_y
        return {
            nid: (x + dx, y + dy)
            for nid, (x, y) in raw_positions.items()
        }

    if algorithm_key == "networkx_spread":
        nx_nodes: list[LayoutNode2D] = [
            LayoutNode2D(
                node_id=nid,
                x=current_positions[nid][0],
                y=current_positions[nid][1],
                width=_size(nid)[0],
                height=_size(nid)[1],
            )
            for nid in ordered_ids
        ]
        id_set = set(ordered_ids)
        nx_edges: list[LayoutEdge2D] = []
        if edge_pairs:
            for idx, (source_id, target_id) in enumerate(edge_pairs):
                if source_id not in id_set or target_id not in id_set:
                    continue
                if source_id == target_id:
                    continue
                nx_edges.append(
                    LayoutEdge2D(
                        edge_id=f"sel_edge_{idx}",
                        source_id=source_id,
                        target_id=target_id,
                    )
                )

        nx_alg = NetworkXSpreadNodeLayoutAlgorithm2D(
            spring_iterations=120,
            spring_k=190.0,
            spread_padding=max(16.0, gap + 6.0),
            spread_iterations=56,
            prevent_shape_overlaps=True,
            shape_overlap_padding=max(12.0, gap),
            shape_overlap_iterations=80,
        )
        raw_positions = nx_alg.compute(nx_nodes, nx_edges)
        if not raw_positions:
            return {}
        center_x = sum(pos[0]
                       for pos in raw_positions.values()) / len(raw_positions)
        center_y = sum(pos[1]
                       for pos in raw_positions.values()) / len(raw_positions)
        dx = cx - center_x
        dy = cy - center_y
        return {
            nid: (x + dx, y + dy)
            for nid, (x, y) in raw_positions.items()
        }

    return dict(current_positions)


__all__ = [
    "LayoutRequest",
    "compact_pack_positions",
    "layout_positions",
]
