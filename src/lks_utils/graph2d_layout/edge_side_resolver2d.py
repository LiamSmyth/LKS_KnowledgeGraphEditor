"""Edge side resolver — derives connector sides from relative node positions."""
from __future__ import annotations

from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["EdgeSideResolver2D"]

# Valid connector sides.
_Side = str  # "left" | "right" | "top" | "bottom"


class EdgeSideResolver2D:
    """Derive the from/to connector side of each edge from node positions.

    The dominant axis of the vector from the source node centre to the
    target node centre determines the sides.  When the vector is
    horizontal the edge exits the right (or left) face; when vertical it
    exits the bottom (or top) face.

    Returns a mapping ``{edge_id: (from_side, to_side)}`` that can be
    stored in :attr:`~lks_utils.graph2d_layout.primitives.LayoutResult2D.edge_sides`.
    """

    def resolve(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
        positions: dict[str, tuple[float, float]],
    ) -> dict[str, tuple[_Side, _Side]]:
        """Compute edge sides.

        Args:
            nodes: All layout nodes (used only to look up sizes).
            edges: Edges to resolve.
            positions: Computed node positions (top-left corner, px).

        Returns:
            Mapping from *edge_id* to *(from_side, to_side)*.
        """
        size_map: dict[str, tuple[float, float]] = {n.node_id: (n.width, n.height) for n in nodes}
        result: dict[str, tuple[_Side, _Side]] = {}

        for edge in edges:
            src = edge.source_id
            dst = edge.target_id
            if src not in positions or dst not in positions:
                result[edge.edge_id] = ("right", "left")
                continue

            sx, sy = positions[src]
            sw, sh = size_map.get(src, (0.0, 0.0))
            dx, dy = positions[dst]
            dw, dh = size_map.get(dst, (0.0, 0.0))

            src_cx = sx + sw * 0.5
            src_cy = sy + sh * 0.5
            dst_cx = dx + dw * 0.5
            dst_cy = dy + dh * 0.5

            rel_x = dst_cx - src_cx
            rel_y = dst_cy - src_cy

            if abs(rel_x) >= abs(rel_y):
                # Dominant axis is horizontal.
                if rel_x >= 0.0:
                    result[edge.edge_id] = ("right", "left")
                else:
                    result[edge.edge_id] = ("left", "right")
            else:
                # Dominant axis is vertical.
                if rel_y >= 0.0:
                    result[edge.edge_id] = ("bottom", "top")
                else:
                    result[edge.edge_id] = ("top", "bottom")

        return result
