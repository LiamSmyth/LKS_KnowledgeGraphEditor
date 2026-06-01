"""Pipeline that chains algorithm → overlap resolver → edge side resolver."""
from __future__ import annotations

from lks_utils.graph2d_layout.edge_side_resolver2d import EdgeSideResolver2D
from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.overlap_resolver2d import OverlapResolver2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D, LayoutResult2D

__all__ = ["Graph2DLayoutPipeline"]


class Graph2DLayoutPipeline:
    """Convenience orchestrator: algorithm + optional post-passes.

    Usage::

        pipeline = Graph2DLayoutPipeline(
            algorithm=SugiyamaNodeLayoutAlgorithm2D(),
            overlap_resolver=OverlapResolver2D(padding=8),
            edge_side_resolver=EdgeSideResolver2D(),
        )
        result = pipeline.run(nodes, edges)
        # result.positions   → dict[node_id, (x, y)]
        # result.edge_sides  → dict[edge_id, (from_side, to_side)]

    Args:
        algorithm: Required layout algorithm.
        overlap_resolver: Optional rect-overlap post-pass.
        edge_side_resolver: Optional edge connector-side deriver.
    """

    def __init__(
        self,
        algorithm: NodeLayoutAlgorithm2D,
        overlap_resolver: OverlapResolver2D | None = None,
        edge_side_resolver: EdgeSideResolver2D | None = None,
    ) -> None:
        self.algorithm = algorithm
        self.overlap_resolver = overlap_resolver
        self.edge_side_resolver = edge_side_resolver

    def run(
        self,
        nodes: list[LayoutNode2D],
        edges: list[LayoutEdge2D],
    ) -> LayoutResult2D:
        """Execute the pipeline and return a :class:`LayoutResult2D`."""
        positions = self.algorithm.compute(nodes, edges)

        if self.overlap_resolver is not None:
            positions = self.overlap_resolver.resolve(nodes, positions)

        edge_sides: dict[str, tuple[str, str]] | None = None
        if self.edge_side_resolver is not None:
            edge_sides = self.edge_side_resolver.resolve(nodes, edges, positions)

        return LayoutResult2D(positions=positions, edge_sides=edge_sides)
