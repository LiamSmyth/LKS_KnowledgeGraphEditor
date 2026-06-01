"""Standalone rect-overlap resolver for 2-D node layouts."""
from __future__ import annotations

from lks_utils.graph2d_layout.primitives import LayoutNode2D

__all__ = ["OverlapResolver2D"]


class OverlapResolver2D:
    """Post-pass rect-overlap separator.

    Runs up to ``max_iterations`` rounds nudging overlapping rectangles
    apart until no overlaps remain or the iteration budget is exhausted.
    Nodes with zero width and height are treated as points and skipped.

    Args:
        padding: Minimum gap maintained between adjacent rects (px).
        max_iterations: Maximum separation rounds.
    """

    def __init__(
        self,
        *,
        padding: float = 8.0,
        max_iterations: int = 32,
    ) -> None:
        self.padding = max(0.0, padding)
        self.max_iterations = max(1, max_iterations)

    def resolve(
        self,
        nodes: list[LayoutNode2D],
        positions: dict[str, tuple[float, float]],
    ) -> dict[str, tuple[float, float]]:
        """Return a copy of *positions* with overlapping rects separated.

        Nodes not in *positions* are ignored.  The input mapping is not
        mutated.
        """
        if not nodes:
            return dict(positions)

        # Filter to nodes that are actually rect-sized.
        rect_nodes = [n for n in nodes if (n.width > 0.0 or n.height > 0.0) and n.node_id in positions]
        if not rect_nodes:
            return dict(positions)

        pos: dict[str, list[float]] = {n.node_id: list(positions[n.node_id]) for n in rect_nodes}
        sizes: dict[str, tuple[float, float]] = {n.node_id: (n.width, n.height) for n in rect_nodes}
        ordered = sorted(pos.keys())
        padding = self.padding

        for _ in range(self.max_iterations):
            moved = False
            for i, a in enumerate(ordered):
                ax, ay = pos[a]
                aw, ah = sizes[a]
                for b in ordered[i + 1:]:
                    bx, by = pos[b]
                    bw, bh = sizes[b]
                    ov_x = min(ax + aw, bx + bw) - max(ax, bx)
                    ov_y = min(ay + ah, by + bh) - max(ay, by)
                    if ov_x <= 0.0 or ov_y <= 0.0:
                        continue
                    moved = True
                    if ov_x <= ov_y:
                        shift = (ov_x + padding) * 0.5
                        acx = ax + aw * 0.5
                        bcx = bx + bw * 0.5
                        dir_x = 1.0 if acx >= bcx else -1.0
                        pos[a][0] += dir_x * shift
                        pos[b][0] -= dir_x * shift
                    else:
                        shift = (ov_y + padding) * 0.5
                        acy = ay + ah * 0.5
                        bcy = by + bh * 0.5
                        dir_y = 1.0 if acy >= bcy else -1.0
                        pos[a][1] += dir_y * shift
                        pos[b][1] -= dir_y * shift
            if not moved:
                break

        result = dict(positions)
        for nid, (x, y) in pos.items():
            result[nid] = (x, y)
        return result
