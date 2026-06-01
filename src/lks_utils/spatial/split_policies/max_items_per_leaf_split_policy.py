"""Split policy: subdivide when item count exceeds a threshold."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lks_utils.spatial.quadtree import QuadtreeNode


class MaxItemsPerLeafSplitPolicy:
    """Split when `len(items) > max_items` and depth allows."""

    def __init__(self, max_items: int = 8, max_depth: int = 12) -> None:
        if max_items < 1:
            raise ValueError(f"max_items must be >= 1, got {max_items}")
        if max_depth < 0:
            raise ValueError(f"max_depth must be >= 0, got {max_depth}")
        self.max_items = max_items
        self.max_depth = max_depth

    def should_split(self, leaf: "QuadtreeNode[Any]") -> bool:
        return len(leaf.items) > self.max_items and leaf.depth < self.max_depth

    def can_subdivide(self, leaf: "QuadtreeNode[Any]") -> bool:
        return leaf.depth < self.max_depth
