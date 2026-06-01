"""Generic 2D quadtree.

Stores arbitrary `T`-typed payloads keyed by axis-aligned bounding boxes.
Pure Python + numpy, no GPU, no Qt, no painter imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Iterator, TypeVar

from lks_utils.spatial.aabb import AABB
from lks_utils.spatial.split_policies.max_items_per_leaf_split_policy import (
    MaxItemsPerLeafSplitPolicy,
)
from lks_utils.spatial.split_policy import SplitPolicy

T = TypeVar("T")


@dataclass(slots=True)
class QuadtreeItem(Generic[T]):
    """An item inserted into the quadtree, identified by AABB + payload."""

    bounds: AABB
    payload: T


@dataclass(slots=True)
class QuadtreeNode(Generic[T]):
    """One node in the quadtree.

    Either a leaf (`children is None`, items live here) or an internal
    node (4 children, items that straddle the split stay here).
    """

    bounds: AABB
    depth: int
    items: list[QuadtreeItem[T]] = field(default_factory=list)
    children: list["QuadtreeNode[T]"] | None = None

    @property
    def is_leaf(self) -> bool:
        return self.children is None

    def iter_leaves(self) -> Iterator["QuadtreeNode[T]"]:
        if self.is_leaf:
            yield self
            return
        assert self.children is not None
        for c in self.children:
            yield from c.iter_leaves()

    def iter_nodes(self) -> Iterator["QuadtreeNode[T]"]:
        yield self
        if self.children is not None:
            for c in self.children:
                yield from c.iter_nodes()


class Quadtree(Generic[T]):
    """Generic 2D quadtree.

    Insertion finds the deepest leaf whose bounds fully contain the
    item's bounds. Items that straddle child boundaries stay at the
    parent. Out-of-bounds inserts raise `ValueError`.
    """

    def __init__(
        self,
        bounds: AABB,
        split_policy: SplitPolicy | None = None,
    ) -> None:
        self._bounds = bounds
        self._policy: SplitPolicy = split_policy or MaxItemsPerLeafSplitPolicy()
        self._root: QuadtreeNode[T] = QuadtreeNode(bounds=bounds, depth=0)

    # -- Public properties -------------------------------------------------

    @property
    def root(self) -> QuadtreeNode[T]:
        return self._root

    @property
    def bounds(self) -> AABB:
        return self._bounds

    # -- Insertion ---------------------------------------------------------

    def insert(self, bounds: AABB, payload: T) -> QuadtreeItem[T]:
        if not self._bounds.contains_aabb(bounds):
            raise ValueError(
                f"Item bounds {bounds} are outside quadtree root {self._bounds}"
            )
        item = QuadtreeItem(bounds=bounds, payload=payload)
        self._insert_into(self._root, item)
        return item

    def insert_point(self, x: float, y: float, payload: T) -> QuadtreeItem[T]:
        return self.insert(AABB.from_point(x, y), payload)

    def _insert_into(self, node: QuadtreeNode[T], item: QuadtreeItem[T]) -> None:
        # If internal, try to descend into a child that fully contains item.
        if not node.is_leaf:
            assert node.children is not None
            for child in node.children:
                if child.bounds.contains_aabb(item.bounds):
                    self._insert_into(child, item)
                    return
            # Straddles children -> stay at this node.
            node.items.append(item)
            return

        # Leaf: append, possibly split.
        node.items.append(item)
        if self._policy.should_split(node) and self._policy.can_subdivide(node):
            self._subdivide(node)

    def _subdivide(self, node: QuadtreeNode[T]) -> None:
        b = node.bounds
        cx, cy = b.cx, b.cy
        # Children layout: NW, NE, SW, SE (Y grows downward by convention,
        # but the tree is agnostic; just any consistent 4-way split).
        children = [
            QuadtreeNode[T](bounds=AABB(b.x0, b.y0, cx, cy),
                            depth=node.depth + 1),
            QuadtreeNode[T](bounds=AABB(cx, b.y0, b.x1, cy),
                            depth=node.depth + 1),
            QuadtreeNode[T](bounds=AABB(b.x0, cy, cx, b.y1),
                            depth=node.depth + 1),
            QuadtreeNode[T](bounds=AABB(cx, cy, b.x1, b.y1),
                            depth=node.depth + 1),
        ]
        # Redistribute items: anything fully contained in a single child
        # moves; straddling stays.
        retained: list[QuadtreeItem[T]] = []
        for item in node.items:
            placed = False
            for child in children:
                if child.bounds.contains_aabb(item.bounds):
                    child.items.append(item)
                    placed = True
                    break
            if not placed:
                retained.append(item)
        node.items = retained
        node.children = children

    # -- Removal -----------------------------------------------------------

    def remove(self, item: QuadtreeItem[T]) -> bool:
        return self._remove_from(self._root, item)

    def _remove_from(
        self, node: QuadtreeNode[T], item: QuadtreeItem[T]
    ) -> bool:
        for i, candidate in enumerate(node.items):
            if candidate is item:
                del node.items[i]
                return True
        if node.children is not None:
            for child in node.children:
                if child.bounds.intersects(item.bounds):
                    if self._remove_from(child, item):
                        return True
        return False

    def clear(self) -> None:
        self._root = QuadtreeNode(bounds=self._bounds, depth=0)

    # -- Queries -----------------------------------------------------------

    def query_point(self, x: float, y: float) -> list[QuadtreeItem[T]]:
        results: list[QuadtreeItem[T]] = []
        self._query_point_into(self._root, x, y, results)
        return results

    def _query_point_into(
        self,
        node: QuadtreeNode[T],
        x: float,
        y: float,
        results: list[QuadtreeItem[T]],
    ) -> None:
        if not node.bounds.contains_point(x, y):
            return
        for item in node.items:
            if item.bounds.contains_point(x, y):
                results.append(item)
        if node.children is not None:
            for c in node.children:
                self._query_point_into(c, x, y, results)

    def query_aabb(self, bounds: AABB) -> list[QuadtreeItem[T]]:
        results: list[QuadtreeItem[T]] = []
        self._query_aabb_into(self._root, bounds, results)
        return results

    def _query_aabb_into(
        self,
        node: QuadtreeNode[T],
        query: AABB,
        results: list[QuadtreeItem[T]],
    ) -> None:
        if not node.bounds.intersects(query):
            return
        for item in node.items:
            if item.bounds.intersects(query):
                results.append(item)
        if node.children is not None:
            for c in node.children:
                self._query_aabb_into(c, query, results)

    def query_circle(
        self, cx: float, cy: float, radius: float
    ) -> list[QuadtreeItem[T]]:
        if radius < 0:
            raise ValueError(f"radius must be >= 0, got {radius}")
        bbox = AABB.from_center(cx, cy, radius)
        candidates = self.query_aabb(bbox)
        r2 = radius * radius
        results: list[QuadtreeItem[T]] = []
        for item in candidates:
            # Closest point in item's bbox to (cx, cy).
            ix = max(item.bounds.x0, min(cx, item.bounds.x1))
            iy = max(item.bounds.y0, min(cy, item.bounds.y1))
            dx = ix - cx
            dy = iy - cy
            if dx * dx + dy * dy <= r2:
                results.append(item)
        return results

    def find_leaf_containing(
        self, x: float, y: float
    ) -> QuadtreeNode[T] | None:
        if not self._bounds.contains_point(x, y):
            return None
        node = self._root
        while not node.is_leaf:
            assert node.children is not None
            for c in node.children:
                if c.bounds.contains_point(x, y):
                    node = c
                    break
            else:
                return node  # straddling point in degenerate case
        return node

    # -- Traversal & inspection -------------------------------------------

    def iter_leaves(self) -> Iterator[QuadtreeNode[T]]:
        yield from self._root.iter_leaves()

    def iter_items(self) -> Iterator[QuadtreeItem[T]]:
        for node in self._root.iter_nodes():
            yield from node.items

    def depth(self) -> int:
        return max((n.depth for n in self._root.iter_nodes()), default=0)

    def leaf_count(self) -> int:
        return sum(1 for _ in self.iter_leaves())

    def item_count(self) -> int:
        return sum(1 for _ in self.iter_items())
