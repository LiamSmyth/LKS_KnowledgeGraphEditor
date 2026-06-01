"""Split-policy protocol for the quadtree.

Policies decide when a leaf should subdivide. Concrete implementations
live in `lks_utils.spatial.split_policies/`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from lks_utils.spatial.quadtree import QuadtreeNode


@runtime_checkable
class SplitPolicy(Protocol):
    """Decides whether a quadtree leaf should subdivide."""

    def should_split(self, leaf: "QuadtreeNode[Any]") -> bool:
        """Return True if this leaf should subdivide on next insert."""
        ...

    def can_subdivide(self, leaf: "QuadtreeNode[Any]") -> bool:
        """Return True if this leaf is allowed to subdivide at all."""
        ...
