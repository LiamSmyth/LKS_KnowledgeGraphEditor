"""Rect-aware grid layout that optimises column count for a target aspect ratio."""
from __future__ import annotations

from math import ceil, sqrt

from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D

__all__ = ["SquarifyGridNodeLayoutAlgorithm2D"]


def _optimal_cols(n: int, cell_w: float, cell_h: float, target_aspect: float) -> int:
    """Return the column count that minimises deviation from *target_aspect*.

    The unconstrained float optimum is ``sqrt(target_aspect * n * cell_h /
    cell_w)``.  A small neighbourhood around that seed is searched so that
    the discretisation effect of ``ceil(n / cols)`` is handled correctly.
    """
    if n <= 1:
        return 1
    float_opt = sqrt(target_aspect * n * cell_h / cell_w)
    seed = max(1, round(float_opt))
    best_err = float("inf")
    result = seed
    for c in range(max(1, seed - 2), min(n, seed + 3)):
        rows = ceil(n / c)
        actual_ar = (c * cell_w) / (rows * cell_h)
        err = abs(actual_ar - target_aspect)
        if err < best_err:
            best_err = err
            result = c
    return result


class SquarifyGridNodeLayoutAlgorithm2D(NodeLayoutAlgorithm2D):
    """Rect-aware grid layout that optimises column count for a target aspect ratio.

    **Tier**: rect-aware — derives cell dimensions from the actual node widths
    and heights so no manual ``col_spacing`` needs to be configured.

    Unlike :class:`GridNodeLayoutAlgorithm2D`, this algorithm:

    * Sizes each grid cell to ``(max_w + gap) × (max_h + gap)`` where
      *max_w* and *max_h* are the largest node dimensions in the input set.
    * Selects the column count that minimises deviation from *target_aspect*
      (default ``1.0`` = square overall cluster).  Pass ``target_aspect=None``
      to fall back to ``ceil(sqrt(n))`` as in the basic grid.
    * Centres the resulting grid at ``(center_x, center_y)``.

    The result is a tightly packed grid with no node overlap (each cell is
    large enough for the widest/tallest node plus the requested gap), and the
    overall cluster shape is as close to *target_aspect* as integer column
    counts allow.

    Args:
        gap: Minimum clear space between adjacent nodes in world units.
            Defaults to a small value; increase for a looser layout.
        target_aspect: Target width/height ratio for the cluster bounding box.
            ``1.0`` = square, ``16/9`` = widescreen, ``None`` = no optimisation
            (uses ``ceil(sqrt(n))`` columns).
        center_x: X coordinate of the grid centre.
        center_y: Y coordinate of the grid centre.
        prevent_shape_overlaps: Run the overlap-resolver post-pass.  Normally
            not needed because the algorithm already guarantees gap-separated
            cells, but can be enabled if downstream transforms may introduce
            overlaps.
        shape_overlap_padding: Extra padding in the overlap post-pass.
        shape_overlap_iterations: Iteration limit for the overlap post-pass.
    """

    def __init__(
        self,
        *,
        gap: float = 8.0,
        target_aspect: float | None = 1.0,
        center_x: float = 0.0,
        center_y: float = 0.0,
        prevent_shape_overlaps: bool = False,
        shape_overlap_padding: float = 8.0,
        shape_overlap_iterations: int = 64,
    ) -> None:
        self.gap = gap
        self.target_aspect = target_aspect
        self.center_x = center_x
        self.center_y = center_y
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

        n = len(nodes)

        # Uniform cell: sized to the largest node dimensions so every node
        # fits without overlap even if sizes vary.
        max_w = max(node.width for node in nodes)
        max_h = max(node.height for node in nodes)
        cell_w = max_w + self.gap
        cell_h = max_h + self.gap

        # Select column count.
        if self.target_aspect is not None:
            cols = _optimal_cols(n, cell_w, cell_h, self.target_aspect)
        else:
            cols = max(1, ceil(sqrt(n)))

        rows = ceil(n / cols)

        # Total cluster dimensions (gap excluded on the outer edge).
        total_w = cols * cell_w - self.gap
        total_h = rows * cell_h - self.gap
        start_x = self.center_x - total_w * 0.5
        start_y = self.center_y - total_h * 0.5

        positions: dict[str, tuple[float, float]] = {}
        for idx, node in enumerate(nodes):
            row = idx // cols
            col = idx % cols
            # Cell centre, then top-left offset per node's own dimensions.
            cell_cx = start_x + col * cell_w + max_w * 0.5
            cell_cy = start_y + row * cell_h + max_h * 0.5
            positions[node.node_id] = (
                cell_cx - node.width * 0.5, cell_cy - node.height * 0.5)

        return self._finalize_positions(
            nodes,
            positions,
            prevent_shape_overlaps=self.prevent_shape_overlaps,
            overlap_padding=self.shape_overlap_padding,
            overlap_iterations=self.shape_overlap_iterations,
        )
