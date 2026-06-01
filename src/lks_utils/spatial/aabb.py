"""Axis-aligned bounding box for 2D spatial indexing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AABB:
    """Axis-aligned bounding box in 2D.

    Closed intervals on both axes: a box that touches another along an
    edge counts as intersecting. Containment is also closed (a box equal
    to another contains it).
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if self.x0 > self.x1:
            raise ValueError(
                f"AABB requires x0 <= x1, got x0={self.x0}, x1={self.x1}")
        if self.y0 > self.y1:
            raise ValueError(
                f"AABB requires y0 <= y1, got y0={self.y0}, y1={self.y1}")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return 0.5 * (self.x0 + self.x1)

    @property
    def cy(self) -> float:
        return 0.5 * (self.y0 + self.y1)

    def contains_point(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def contains_aabb(self, other: AABB) -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and self.x1 >= other.x1
            and self.y1 >= other.y1
        )

    def intersects(self, other: AABB) -> bool:
        return not (
            other.x1 < self.x0
            or other.x0 > self.x1
            or other.y1 < self.y0
            or other.y0 > self.y1
        )

    def union(self, other: AABB) -> AABB:
        return AABB(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    @classmethod
    def from_point(cls, x: float, y: float) -> AABB:
        return cls(x, y, x, y)

    @classmethod
    def from_center(cls, cx: float, cy: float, half: float) -> AABB:
        if half < 0:
            raise ValueError(f"half must be >= 0, got {half}")
        return cls(cx - half, cy - half, cx + half, cy + half)
