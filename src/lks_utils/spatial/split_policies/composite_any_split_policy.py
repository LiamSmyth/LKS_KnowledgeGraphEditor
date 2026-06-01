"""Split policy: split if ANY child policy votes split."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lks_utils.spatial.split_policy import SplitPolicy

if TYPE_CHECKING:
    from lks_utils.spatial.quadtree import QuadtreeNode


class CompositeAnyPolicy:
    """Combine policies: split if any votes; subdivide if all allow."""

    def __init__(self, *policies: SplitPolicy) -> None:
        if not policies:
            raise ValueError("CompositeAnyPolicy requires at least one policy")
        self.policies = policies

    def should_split(self, leaf: "QuadtreeNode[Any]") -> bool:
        return any(p.should_split(leaf) for p in self.policies)

    def can_subdivide(self, leaf: "QuadtreeNode[Any]") -> bool:
        return all(p.can_subdivide(leaf) for p in self.policies)
