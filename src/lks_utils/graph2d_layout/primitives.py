"""Primitive data types for the graph2d_layout module."""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "LayoutNode2D",
    "LayoutEdge2D",
    "LayoutResult2D",
]


@dataclass
class LayoutNode2D:
    """A node to be positioned by a layout algorithm.

    ``x`` and ``y`` are optional hints for the initial position (e.g.
    the current canvas position before a re-layout). Algorithms may or
    may not use them for seeding.

    ``width`` and ``height`` are used by rect-aware and graph-aware
    algorithms to compute spacing and overlap resolution. Algorithms
    that only need point positions (e.g. circular) ignore them.
    """

    node_id: str
    x: float = 0.0
    y: float = 0.0
    width: float = 180.0
    height: float = 90.0


@dataclass
class LayoutEdge2D:
    """A directed edge between two nodes in the layout graph."""

    edge_id: str
    source_id: str
    target_id: str


@dataclass
class LayoutResult2D:
    """The output of a layout pipeline run.

    ``positions`` maps each ``node_id`` to its computed ``(x, y)``
    world-space position (top-left corner).

    ``edge_sides`` is optional. When the pipeline includes an
    :class:`~lks_utils.graph2d_layout.edge_side_resolver2d.EdgeSideResolver2D`
    pass, this dict maps each ``edge_id`` to a ``(from_side, to_side)``
    tuple where side values are ``"left"``, ``"right"``, ``"top"``, or
    ``"bottom"``.
    """

    positions: dict[str, tuple[float, float]] = field(default_factory=dict)
    edge_sides: dict[str, tuple[str, str]] | None = None
