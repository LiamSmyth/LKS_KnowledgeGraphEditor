"""graph2d_layout — pure-Python 2-D node layout algorithms.

This module provides a small suite of layout algorithms for positioning
2-D nodes (with optional edge topology and rect sizes).  It is
framework-agnostic: no Qt, no PyFlow.  A separate adapter class
bridges the module to Canvas2D items.

Public API
----------
Primitives:
    :class:`LayoutNode2D`, :class:`LayoutEdge2D`, :class:`LayoutResult2D`

Base class:
    :class:`NodeLayoutAlgorithm2D`

Algorithms (in ``algorithms`` sub-package):
    :class:`GridNodeLayoutAlgorithm2D`           — points-only grid
    :class:`NetworkXSpreadNodeLayoutAlgorithm2D` — graph-aware spring + rect-spread
    :class:`SquarifyGridNodeLayoutAlgorithm2D`   — rect-aware grid, aspect-ratio optimised
    :class:`CircularNodeLayoutAlgorithm2D`       — points-only circle
    :class:`SugiyamaNodeLayoutAlgorithm2D`   — graph-aware layered
    :class:`ForceDirectedNodeLayoutAlgorithm2D` — graph-aware physics
    :class:`TreeNodeLayoutAlgorithm2D`       — rooted tree / forest

Post-pass helpers:
    :class:`OverlapResolver2D`    — rect-overlap separator
    :class:`EdgeSideResolver2D`   — connector-side deriver

Orchestration:
    :class:`Graph2DLayoutPipeline`

Canvas2D bridge:
    :class:`Canvas2DGraphLayoutAdapter`
"""
from __future__ import annotations

from lks_utils.graph2d_layout.algorithms.circular_node_layout_algorithm2d import (
    CircularNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.constrained_force_directed_node_layout_algorithm2d import (
    ConstrainedForceDirectedNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.force_directed_node_layout_algorithm2d import (
    ForceDirectedNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.grid_node_layout_algorithm2d import (
    GridNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.lane_node_layout_algorithm2d import (
    LaneNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.networkx_spread_node_layout_algorithm2d import (
    NetworkXSpreadNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.squarify_grid_node_layout_algorithm2d import (
    SquarifyGridNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.sugiyama_node_layout_algorithm2d import (
    SugiyamaNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.algorithms.tree_node_layout_algorithm2d import (
    TreeNodeLayoutAlgorithm2D,
)
from lks_utils.graph2d_layout.canvas2d_graph_layout_adapter import (
    Canvas2DGraphLayoutAdapter,
)
from lks_utils.graph2d_layout.edge_side_resolver2d import EdgeSideResolver2D
from lks_utils.graph2d_layout.graph2d_layout_pipeline import Graph2DLayoutPipeline
from lks_utils.graph2d_layout.node_layout_algorithm2d import NodeLayoutAlgorithm2D
from lks_utils.graph2d_layout.overlap_resolver2d import OverlapResolver2D
from lks_utils.graph2d_layout.primitives import LayoutEdge2D, LayoutNode2D, LayoutResult2D

__all__ = [
    # Primitives
    "LayoutNode2D",
    "LayoutEdge2D",
    "LayoutResult2D",
    # Base class
    "NodeLayoutAlgorithm2D",
    # Algorithms
    "GridNodeLayoutAlgorithm2D",
    "NetworkXSpreadNodeLayoutAlgorithm2D",
    "SquarifyGridNodeLayoutAlgorithm2D",
    "CircularNodeLayoutAlgorithm2D",
    "ConstrainedForceDirectedNodeLayoutAlgorithm2D",
    "SugiyamaNodeLayoutAlgorithm2D",
    "ForceDirectedNodeLayoutAlgorithm2D",
    "LaneNodeLayoutAlgorithm2D",
    "TreeNodeLayoutAlgorithm2D",
    # Post-passes
    "OverlapResolver2D",
    "EdgeSideResolver2D",
    # Orchestration
    "Graph2DLayoutPipeline",
    # Canvas2D bridge
    "Canvas2DGraphLayoutAdapter",
]
