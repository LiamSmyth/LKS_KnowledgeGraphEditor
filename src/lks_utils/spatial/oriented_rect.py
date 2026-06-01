"""`OrientedRect`: rotation-aware 2-D rectangle (frozen value object).

Defines a rectangle by its centre, half-extents, and orientation.
Pure geometry — no Qt, no GPU.

Typical use-cases: bounding volumes for rotated items, hit-testing
text labels and sprites, orienting brush footprints.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from lks_utils.spatial.aabb import AABB


@dataclass(frozen=True, slots=True)
class OrientedRect:
    """An axis-aligned rectangle that has been rotated in 2-D.

    Attributes:
        centre:           (cx, cy) world-space centre.
        half_extents:     (hx, hy) half-widths along the *local* axes
                          (before rotation).
        rotation_radians: CCW rotation around ``centre``.
    """

    centre: tuple[float, float]
    half_extents: tuple[float, float]
    rotation_radians: float = 0.0

    # ------------------------------------------------------------------ #
    # Geometry queries                                                     #
    # ------------------------------------------------------------------ #

    def corners(self) -> tuple[tuple[float, float], ...]:
        """Return the four corners in counter-clockwise order (Y-up).

        Corner order (local space before rotation):

            0: (-hx, -hy)  bottom-left
            1: ( hx, -hy)  bottom-right
            2: ( hx,  hy)  top-right
            3: (-hx,  hy)  top-left

        Traversing them in order gives a CCW polygon in Y-up world space.
        """
        cx, cy = self.centre
        hx, hy = self.half_extents
        cos_r = math.cos(self.rotation_radians)
        sin_r = math.sin(self.rotation_radians)
        local = ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))
        result = []
        for lx, ly in local:
            rx = cos_r * lx - sin_r * ly
            ry = sin_r * lx + cos_r * ly
            result.append((cx + rx, cy + ry))
        return tuple(result)

    def to_aabb(self) -> AABB:
        """Return the axis-aligned bounding box of the four corners."""
        pts = self.corners()
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return AABB(min(xs), min(ys), max(xs), max(ys))

    def contains_point(self, p: tuple[float, float]) -> bool:
        """Return True if *p* is inside (or on the border of) this rect.

        Uses inverse rotation into local space for an exact test.
        """
        cx, cy = self.centre
        px, py = p
        dx = px - cx
        dy = py - cy
        # Rotate *into* local space (negate rotation).
        cos_r = math.cos(-self.rotation_radians)
        sin_r = math.sin(-self.rotation_radians)
        lx = cos_r * dx - sin_r * dy
        ly = sin_r * dx + cos_r * dy
        hx, hy = self.half_extents
        return -hx <= lx <= hx and -hy <= ly <= hy


__all__ = ["OrientedRect"]
