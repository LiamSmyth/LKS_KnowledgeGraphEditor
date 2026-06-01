"""Generic 2D spatial index module.

Public API:
- AABB: axis-aligned bounding box
- Quadtree, QuadtreeNode, QuadtreeItem: generic 2D quadtree
- SplitPolicy: protocol; concrete: MaxItemsPerLeafSplitPolicy,
  MaxDepthSplitPolicy, CompositeAnyPolicy
- Transform2D: immutable 2-D similarity transform (translate + rotate + scale)
- OrientedRect: rotation-aware 2-D rectangle (frozen value)
"""
from __future__ import annotations

from lks_utils.spatial.aabb import AABB
from lks_utils.spatial.oriented_rect import OrientedRect
from lks_utils.spatial.quadtree import Quadtree, QuadtreeItem, QuadtreeNode
from lks_utils.spatial.split_policies import (
    CompositeAnyPolicy,
    MaxDepthSplitPolicy,
    MaxItemsPerLeafSplitPolicy,
)
from lks_utils.spatial.split_policy import SplitPolicy
from lks_utils.spatial.transform2d import Transform2D

__all__ = [
    "AABB",
    "CompositeAnyPolicy",
    "MaxDepthSplitPolicy",
    "MaxItemsPerLeafSplitPolicy",
    "OrientedRect",
    "Quadtree",
    "QuadtreeItem",
    "QuadtreeNode",
    "SplitPolicy",
    "Transform2D",
]
