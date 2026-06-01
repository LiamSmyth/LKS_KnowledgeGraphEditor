"""MonotonicSplineCurve — height-safe constrained spline curve.

This subclass of :class:`~lks_utils.curve.spline_curve.SplineCurve` enforces:

- Pinned endpoints at ``(0, 0)`` and ``(1, 1)`` (x-locked; y can be adjusted).
- Strict x-monotonicity: every point must have a *strictly greater* x than its
  predecessor, so the curve is always single-valued.
- Y-monotonicity enforcement: when moving a point, y is clamped so that the
  curve never decreases.  This prevents loopback curves.

Use this for height remapping, blend mask falloffs, and any context where a
non-monotonic curve would produce undefined or artist-hostile results.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from lks_utils.curve.spline_curve import SplineCurve
from lks_utils.curve.spline_point import PointType, SplinePoint


class MonotonicSplineCurve(SplineCurve):
    """A :class:`SplineCurve` restricted to monotonically non-decreasing curves.

    Mutation methods apply additional clamping to preserve the monotonic
    property.  Serialization round-trips preserve the constraint type via
    the ``"monotonic"`` flag in the dict.
    """

    # ------------------------------------------------------------------ #
    # Mutation (override with constraint)                                  #
    # ------------------------------------------------------------------ #

    def add_point(
        self,
        x: float,
        y: float,
        point_type: PointType = PointType.LINEAR,
    ) -> int:
        """Insert a point only if it doesn't violate y-monotonicity."""
        x = float(np.clip(x, 1e-5, 1.0 - 1e-5))
        y = float(np.clip(y, 0.0, 1.0))

        # Find where this point would fall
        pts = self._points
        xs = [p.x for p in pts]
        import bisect
        idx = bisect.bisect_left(xs, x)

        # Clamp y to [y_prev, y_next]
        y_min = pts[max(0, idx - 1)].y
        y_max = pts[min(len(pts) - 1, idx)].y
        y = float(np.clip(y, y_min, y_max))
        return super().add_point(x, y, point_type)

    def move_point(self, index: int, x: float, y: float) -> int:
        """Move a point with monotonicity enforcement.

        ``x`` is clamped between the predecessor's and successor's x positions.
        ``y`` is clamped to stay non-decreasing relative to its neighbors.

        Returns the new index after any re-sort.
        """
        pts = self._points
        n = len(pts)
        x = float(x)
        y = float(np.clip(y, 0.0, 1.0))

        # Lock endpoint x coordinates
        if index == 0:
            x = 0.0
        elif index == n - 1:
            x = 1.0
        else:
            # Clamp x strictly between neighbors
            x_lo = pts[index - 1].x + 1e-5
            x_hi = pts[index + 1].x - 1e-5
            x = float(np.clip(x, x_lo, x_hi))

        # Clamp y between neighbors
        y_lo = pts[max(0, index - 1)].y
        y_hi = pts[min(n - 1, index + 1)].y
        y = float(np.clip(y, y_lo, y_hi))

        return super().move_point(index, x, y)

    def is_valid_monotonic(self) -> bool:
        """Return True if the curve is currently monotonically non-decreasing."""
        pts = self._points
        for i in range(len(pts) - 1):
            if pts[i + 1].y < pts[i].y - 1e-6:
                return False
        return True

    # ------------------------------------------------------------------ #
    # Serialization                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["monotonic"] = True
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MonotonicSplineCurve:  # type: ignore[override]
        """Deserialize; always returns a MonotonicSplineCurve regardless of flag."""
        curve = cls.__new__(cls)
        from lks_utils.curve.spline_point import SplinePoint
        curve._points = [SplinePoint.from_dict(p) for p in data.get("points", [])]
        if not curve._points:
            curve._points = [
                SplinePoint(0.0, 0.0, PointType.LINEAR),
                SplinePoint(1.0, 1.0, PointType.LINEAR),
            ]
        return curve

    def copy(self) -> MonotonicSplineCurve:  # type: ignore[override]
        return MonotonicSplineCurve.from_dict(self.to_dict())


def is_monotonic_dict(data: dict[str, Any]) -> bool:
    """Return True if a serialized curve dict has the monotonic flag set."""
    return bool(data.get("monotonic", False))


__all__ = ["MonotonicSplineCurve", "is_monotonic_dict"]
