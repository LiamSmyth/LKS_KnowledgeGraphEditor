"""Concrete split policies for the quadtree."""
from __future__ import annotations

from lks_utils.spatial.split_policies.composite_any_split_policy import (
    CompositeAnyPolicy,
)
from lks_utils.spatial.split_policies.max_depth_split_policy import (
    MaxDepthSplitPolicy,
)
from lks_utils.spatial.split_policies.max_items_per_leaf_split_policy import (
    MaxItemsPerLeafSplitPolicy,
)

__all__ = [
    "CompositeAnyPolicy",
    "MaxDepthSplitPolicy",
    "MaxItemsPerLeafSplitPolicy",
]
