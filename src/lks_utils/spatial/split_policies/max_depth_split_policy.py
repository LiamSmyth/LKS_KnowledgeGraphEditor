"""Split policy: never split past max_depth, always split below it.

Useful as a "force-uniform-depth" policy or as a guardrail combined with
other policies via `CompositeAnyPolicy`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lks_utils.spatial.quadtree import QuadtreeNode


class MaxDepthSplitPolicy:
    """Always vote split below max_depth; never at or beyond."""

    def __init__(self, max_depth: int) -> None:
        if max_depth < 0:
            raise ValueError(f"max_depth must be >= 0, got {max_depth}")
        self.max_depth = max_depth

    def should_split(self, leaf: "QuadtreeNode[Any]") -> bool:
        return leaf.depth < self.max_depth

    def can_subdivide(self, leaf: "QuadtreeNode[Any]") -> bool:
        return leaf.depth < self.max_depth
