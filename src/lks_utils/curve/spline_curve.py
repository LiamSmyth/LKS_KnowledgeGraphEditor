"""SplineCurve — generic piecewise spline curve over the [0,1]×[0,1] square.

Supports linear, cubic Bézier, and uniform cubic B-spline segments.
Evaluation is always single-valued (each x maps to exactly one y) for
standard usage, though no monotonicity is enforced here — see
:class:`~lks_utils.curve.monotonic_spline_curve.MonotonicSplineCurve` for
the constrained variant.
"""
from __future__ import annotations

import bisect
from typing import Any

import numpy as np

from lks_utils.curve.spline_point import PointType, SplinePoint, TangentMode


def _solve_bezier_t(x0: float, x1: float, x2: float, x3: float, x: float) -> float:
    """Find t in [0, 1] such that the cubic Bézier X(t) ≈ x.

    Uses Newton-Raphson (up to 8 steps) with a 32-step bisection fallback for
    robustness against degenerate or non-monotonic X parameterisations.
    """
    if x <= x0:
        return 0.0
    if x >= x3:
        return 1.0

    # Initial guess from linear reparametrisation
    dx = x3 - x0
    t = (x - x0) / dx if dx > 1e-10 else 0.5
    t = float(np.clip(t, 0.0, 1.0))

    # Newton-Raphson
    for _ in range(8):
        mt = 1.0 - t
        xt = mt**3 * x0 + 3.0 * mt**2 * t * x1 + 3.0 * mt * t**2 * x2 + t**3 * x3
        dxt = 3.0 * mt**2 * (x1 - x0) + 6.0 * mt * t * \
            (x2 - x1) + 3.0 * t**2 * (x3 - x2)
        f = xt - x
        if abs(f) < 1e-7:
            return float(np.clip(t, 0.0, 1.0))
        if abs(dxt) < 1e-10:
            break
        t = float(np.clip(t - f / dxt, 0.0, 1.0))

    # Bisection fallback (32 steps ≈ 3e-10 precision on [0, 1])
    lo, hi = 0.0, 1.0
    for _ in range(32):
        mid = (lo + hi) * 0.5
        mt = 1.0 - mid
        xm = mt**3 * x0 + 3.0 * mt**2 * mid * x1 + 3.0 * mt * mid**2 * x2 + mid**3 * x3
        if xm < x:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


class SplineCurve:
    """A 2-D piecewise spline curve in the unit square.

    The curve is defined by an ordered list of :class:`SplinePoint` objects
    sorted by their ``x`` value.  The first and last points are treated as
    *endpoints* — they cannot be removed, and their ``x`` values are
    clamped to ``0.0`` and ``1.0`` respectively.

    Segment interpolation type is derived from both endpoint types:

    - ``LINEAR``:  straight line (both endpoints non-Bézier).
    - ``BEZIER``:  full 2-D parametric cubic Bézier — solves ``X(t) = x``
                   then evaluates ``Y(t)`` — activated whenever *either*
                   endpoint is ``BEZIER``.  When only one endpoint carries
                   handles, a proportional neutral default is used for the
                   handleless side.
    - ``BSPLINE``: uniform cubic B-spline blending four consecutive points
                   (determined by the *left* point's type; takes precedence
                   over a Bézier right neighbour).

    Example::

        curve = SplineCurve()
        curve.add_point(0.25, 0.1)
        y = curve.evaluate(0.5)
    """

    def __init__(self) -> None:
        # Two pinned endpoints — (0,0) and (1,1)
        self._points: list[SplinePoint] = [
            SplinePoint(0.0, 0.0, PointType.LINEAR),
            SplinePoint(1.0, 1.0, PointType.LINEAR),
        ]

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def points(self) -> list[SplinePoint]:
        """Read-only view of the ordered control-point list."""
        return list(self._points)

    def __len__(self) -> int:
        return len(self._points)

    # ------------------------------------------------------------------ #
    # Mutation                                                             #
    # ------------------------------------------------------------------ #

    def add_point(
        self,
        x: float,
        y: float,
        point_type: PointType = PointType.LINEAR,
    ) -> int:
        """Insert a new control point and return its index.

        The list remains sorted by ``x``.  The endpoints (indices 0 and -1)
        are never displaced — ``x`` is clamped to ``(0, 1)`` exclusive.
        """
        x = float(np.clip(x, 0.0, 1.0))
        y = float(np.clip(y, 0.0, 1.0))
        # Don't insert on top of an existing endpoint
        if x == 0.0 or x == 1.0:
            return 0 if x == 0.0 else len(self._points) - 1

        pt = SplinePoint(x, y, point_type)
        # Bisect on x to find insertion position
        xs = [p.x for p in self._points]
        idx = bisect.bisect_left(xs, x)
        # If exact duplicate x — bump very slightly to keep order
        if idx < len(self._points) and self._points[idx].x == x:
            x = min(x + 1e-5, 1.0 - 1e-5)
            pt = SplinePoint(x, y, point_type)
            idx = bisect.bisect_left([p.x for p in self._points], x)
        self._points.insert(idx, pt)
        return idx

    def remove_point(self, index: int) -> None:
        """Remove a control point by index.  Endpoints (0, last) are protected."""
        if index <= 0 or index >= len(self._points) - 1:
            return
        self._points.pop(index)

    def move_point(self, index: int, x: float, y: float) -> int:
        """Reposition a control point; re-sort if x ordering changes.

        Returns the new index of the moved point.
        """
        x = float(np.clip(x, 0.0, 1.0))
        y = float(np.clip(y, 0.0, 1.0))

        # Lock endpoints to their x
        if index == 0:
            x = 0.0
        elif index == len(self._points) - 1:
            x = 1.0

        pt = self._points[index]
        new_pt = SplinePoint(
            x,
            y,
            pt.point_type,
            pt.handle_in,
            pt.handle_out,
            pt.tangent_in_mode,
            pt.tangent_out_mode,
        )

        self._points.pop(index)
        xs = [p.x for p in self._points]
        new_idx = bisect.bisect_left(xs, x)
        # Clamp so endpoints stay at boundaries
        new_idx = max(0, min(new_idx, len(self._points)))
        self._points.insert(new_idx, new_pt)
        return new_idx

    def set_point_type(self, index: int, point_type: PointType) -> None:
        """Change the interpolation type of a point and init default handles."""
        if index < 0 or index >= len(self._points):
            return
        pt = self._points[index]
        prev_type = pt.point_type
        hi = pt.handle_in
        ho = pt.handle_out
        t_in = pt.tangent_in_mode
        t_out = pt.tangent_out_mode
        if point_type == PointType.BEZIER:
            # When entering Bezier mode, initialize auto tangents based on
            # neighboring segment direction (not flat horizontal handles).
            if prev_type != PointType.BEZIER:
                hi, ho = self._compute_auto_handles(index)
                t_in = TangentMode.AUTO
                t_out = TangentMode.AUTO
            else:
                if ho is None:
                    ho = (0.1, 0.0)
                if hi is None:
                    hi = (-0.1, 0.0)
        else:
            hi = None
            ho = None
            t_in = TangentMode.BROKEN
            t_out = TangentMode.BROKEN
        self._points[index] = SplinePoint(
            pt.x,
            pt.y,
            point_type,
            hi,
            ho,
            t_in,
            t_out,
        )

    def _compute_auto_handles(self, index: int) -> tuple[tuple[float, float], tuple[float, float]]:
        """Compute balanced in/out auto handles for a control point.

        Tangent direction is derived from the local polyline direction so the
        handles are angled consistently with incoming/outgoing segments.
        """
        n = len(self._points)
        p = self._points[index]
        if n < 2:
            return (-0.1, 0.0), (0.1, 0.0)

        if index == 0:
            nxt = self._points[1]
            dx = nxt.x - p.x
            dy = nxt.y - p.y
            len_out = max(1e-4, np.hypot(dx, dy) / 3.0)
            mag = np.hypot(dx, dy)
            if mag < 1e-8:
                return (-0.1, 0.0), (0.1, 0.0)
            ux = dx / mag
            uy = dy / mag
            return (-ux * len_out, -uy * len_out), (ux * len_out, uy * len_out)

        if index == n - 1:
            prv = self._points[n - 2]
            dx = p.x - prv.x
            dy = p.y - prv.y
            len_in = max(1e-4, np.hypot(dx, dy) / 3.0)
            mag = np.hypot(dx, dy)
            if mag < 1e-8:
                return (-0.1, 0.0), (0.1, 0.0)
            ux = dx / mag
            uy = dy / mag
            return (-ux * len_in, -uy * len_in), (ux * len_in, uy * len_in)

        prv = self._points[index - 1]
        nxt = self._points[index + 1]
        dx = nxt.x - prv.x
        dy = nxt.y - prv.y
        mag = np.hypot(dx, dy)
        if mag < 1e-8:
            return (-0.1, 0.0), (0.1, 0.0)

        ux = dx / mag
        uy = dy / mag
        len_in = max(1e-4, np.hypot(p.x - prv.x, p.y - prv.y) / 3.0)
        len_out = max(1e-4, np.hypot(nxt.x - p.x, nxt.y - p.y) / 3.0)

        return (-ux * len_in, -uy * len_in), (ux * len_out, uy * len_out)

    def cycle_tangent_mode(self, index: int, which: str) -> TangentMode:
        """Cycle one handle side between BROKEN, ALIGNED, and AUTO.

        Args:
            index: Control point index.
            which: ``"in"`` or ``"out"``.

        Returns:
            The new tangent mode for the selected side.
        """
        if index < 0 or index >= len(self._points):
            return TangentMode.BROKEN

        pt = self._points[index]
        if pt.point_type != PointType.BEZIER:
            return TangentMode.BROKEN

        def _next_mode(mode: TangentMode) -> TangentMode:
            order = [TangentMode.BROKEN, TangentMode.ALIGNED, TangentMode.AUTO]
            return order[(order.index(mode) + 1) % len(order)]

        if which == "in":
            new_mode = _next_mode(pt.tangent_in_mode)
            new_pt = SplinePoint(
                pt.x,
                pt.y,
                pt.point_type,
                pt.handle_in,
                pt.handle_out,
                new_mode,
                pt.tangent_out_mode,
            )
            self._points[index] = new_pt
            if new_mode in (TangentMode.ALIGNED, TangentMode.AUTO) and new_pt.handle_in is not None:
                self._sync_opposite_handle(
                    index, "in", new_pt.handle_in, new_mode)
            return new_mode

        new_mode = _next_mode(pt.tangent_out_mode)
        new_pt = SplinePoint(
            pt.x,
            pt.y,
            pt.point_type,
            pt.handle_in,
            pt.handle_out,
            pt.tangent_in_mode,
            new_mode,
        )
        self._points[index] = new_pt
        if new_mode in (TangentMode.ALIGNED, TangentMode.AUTO) and new_pt.handle_out is not None:
            self._sync_opposite_handle(
                index, "out", new_pt.handle_out, new_mode)
        return new_mode

    def _sync_opposite_handle(
        self,
        index: int,
        moved_side: str,
        moved: tuple[float, float],
        mode: TangentMode,
    ) -> None:
        """Update opposite handle using ALIGNED or AUTO tangent behavior."""
        pt = self._points[index]
        mx, my = moved
        mag = float(np.hypot(mx, my))

        # If the moved handle collapses to zero, collapse opposite as well.
        if mag < 1e-8:
            opposite = (0.0, 0.0)
        else:
            ux = -mx / mag
            uy = -my / mag
            if moved_side == "in":
                current_opposite = pt.handle_out
            else:
                current_opposite = pt.handle_in

            if mode == TangentMode.AUTO:
                out_len = mag
            else:
                # ALIGNED: preserve opposite side length while mirroring direction.
                if current_opposite is None:
                    out_len = mag
                else:
                    out_len = float(
                        np.hypot(current_opposite[0], current_opposite[1]))
            opposite = (ux * out_len, uy * out_len)

        if moved_side == "in":
            self._points[index] = SplinePoint(
                pt.x,
                pt.y,
                pt.point_type,
                pt.handle_in,
                opposite,
                pt.tangent_in_mode,
                pt.tangent_out_mode,
            )
        else:
            self._points[index] = SplinePoint(
                pt.x,
                pt.y,
                pt.point_type,
                opposite,
                pt.handle_out,
                pt.tangent_in_mode,
                pt.tangent_out_mode,
            )

    def move_handle(
        self,
        index: int,
        which: str,
        dx: float,
        dy: float,
    ) -> None:
        """Move a Bézier handle (relative offset from the control point).

        Args:
            index: Control point index.
            which: ``"in"`` or ``"out"``.
            dx:    New relative x offset.
            dy:    New relative y offset.
        """
        if index < 0 or index >= len(self._points):
            return
        pt = self._points[index]
        if which == "out":
            self._points[index] = SplinePoint(
                pt.x,
                pt.y,
                pt.point_type,
                pt.handle_in,
                (dx, dy),
                pt.tangent_in_mode,
                pt.tangent_out_mode,
            )
            if pt.tangent_out_mode in (TangentMode.ALIGNED, TangentMode.AUTO):
                self._sync_opposite_handle(
                    index,
                    "out",
                    (dx, dy),
                    pt.tangent_out_mode,
                )
        else:
            self._points[index] = SplinePoint(
                pt.x,
                pt.y,
                pt.point_type,
                (dx, dy),
                pt.handle_out,
                pt.tangent_in_mode,
                pt.tangent_out_mode,
            )
            if pt.tangent_in_mode in (TangentMode.ALIGNED, TangentMode.AUTO):
                self._sync_opposite_handle(
                    index,
                    "in",
                    (dx, dy),
                    pt.tangent_in_mode,
                )

    # ------------------------------------------------------------------ #
    # Transforms                                                           #
    # ------------------------------------------------------------------ #

    def flip_horizontal(self) -> None:
        """Mirror the curve left↔right (x → 1 − x)."""
        new_pts: list[SplinePoint] = []
        for pt in reversed(self._points):
            hi = (-pt.handle_out[0], -pt.handle_out[1]
                  ) if pt.handle_out else None
            ho = (-pt.handle_in[0], -pt.handle_in[1]) if pt.handle_in else None
            new_pts.append(
                SplinePoint(
                    1.0 - pt.x,
                    pt.y,
                    pt.point_type,
                    hi,
                    ho,
                    pt.tangent_out_mode,
                    pt.tangent_in_mode,
                )
            )
        self._points = new_pts

    def flip_vertical(self) -> None:
        """Mirror the curve up↔down (y → 1 − y)."""
        new_pts: list[SplinePoint] = []
        for pt in self._points:
            hi = (pt.handle_in[0], -pt.handle_in[1]) if pt.handle_in else None
            ho = (pt.handle_out[0], -pt.handle_out[1]
                  ) if pt.handle_out else None
            new_pts.append(
                SplinePoint(
                    pt.x,
                    1.0 - pt.y,
                    pt.point_type,
                    hi,
                    ho,
                    pt.tangent_in_mode,
                    pt.tangent_out_mode,
                )
            )
        self._points = new_pts

    def reset(self) -> None:
        """Reset to the linear identity curve (two endpoint-only points)."""
        self._points = [
            SplinePoint(0.0, 0.0, PointType.LINEAR),
            SplinePoint(1.0, 1.0, PointType.LINEAR),
        ]

    # ------------------------------------------------------------------ #
    # Evaluation                                                           #
    # ------------------------------------------------------------------ #

    def evaluate(self, x: float) -> float:
        """Evaluate the curve at a single ``x`` position.

        Returns a ``y`` value in ``[0, 1]``.
        """
        x = float(np.clip(x, 0.0, 1.0))
        pts = self._points
        n = len(pts)
        if n == 1:
            return float(pts[0].y)

        # Find segment [i, i+1] that contains x
        if x <= pts[0].x:
            return float(pts[0].y)
        if x >= pts[-1].x:
            return float(pts[-1].y)

        seg_idx = 0
        for i in range(n - 1):
            if pts[i].x <= x <= pts[i + 1].x:
                seg_idx = i
                break

        p0 = pts[seg_idx]
        p1 = pts[seg_idx + 1]

        # Local t within segment
        dx = p1.x - p0.x
        t = 0.0 if dx < 1e-10 else (x - p0.x) / dx

        # Segment is Bezier when either endpoint is BEZIER; BSPLINE from
        # the left point only (takes precedence over a Bezier right neighbour).
        if p0.point_type == PointType.BSPLINE:
            return self._eval_bspline(seg_idx, t)
        if p0.point_type == PointType.BEZIER or p1.point_type == PointType.BEZIER:
            return self._eval_bezier(p0, p1, x)
        # LINEAR (default)
        return float(p0.y + (p1.y - p0.y) * t)

    def evaluate_array(self, arr: np.ndarray) -> np.ndarray:
        """Vectorized evaluate using a LUT for performance.

        Args:
            arr: Float32 / float64 array of x values in ``[0, 1]``.

        Returns:
            Float32 array of y values with the same shape as ``arr``.
        """
        lut = self.to_lut(1024)
        indices = np.clip(
            (arr * (len(lut) - 1)).astype(np.int32), 0, len(lut) - 1)
        return lut[indices].astype(np.float32)

    def to_lut(self, size: int = 256) -> np.ndarray:
        """Sample the curve into a 1-D LUT of the given size.

        Args:
            size: Number of equally-spaced samples from 0 to 1.

        Returns:
            Float32 array of shape ``(size,)`` with y values.
        """
        xs = np.linspace(0.0, 1.0, size, dtype=np.float32)
        return np.array([self.evaluate(float(x)) for x in xs], dtype=np.float32)

    # ------------------------------------------------------------------ #
    # Segment evaluation helpers                                           #
    # ------------------------------------------------------------------ #

    def _eval_bezier(
        self, p0: SplinePoint, p1: SplinePoint, x: float
    ) -> float:
        """Full 2-D cubic Bézier: solve X(t) = x then return Y(t).

        Both handle components (dx, dy) influence the curve shape.  When an
        endpoint carries no handle (e.g. a LINEAR point adjacent to a BEZIER
        point), a proportional neutral default is used so the other
        endpoint's handle still shapes the curve correctly.
        """
        seg_dx = p1.x - p0.x
        ho = p0.handle_out if p0.handle_out is not None else (
            seg_dx / 3.0, 0.0)
        hi = p1.handle_in if p1.handle_in is not None else (-seg_dx / 3.0, 0.0)

        x0, y0 = p0.x, p0.y
        x1, y1 = p0.x + ho[0], p0.y + ho[1]
        x2, y2 = p1.x + hi[0], p1.y + hi[1]
        x3, y3 = p1.x, p1.y

        t = _solve_bezier_t(x0, x1, x2, x3, x)
        mt = 1.0 - t
        y = mt**3 * y0 + 3.0 * mt**2 * t * y1 + 3.0 * mt * t**2 * y2 + t**3 * y3
        return float(np.clip(y, 0.0, 1.0))

    def _eval_bspline(self, seg_idx: int, t: float) -> float:
        """Uniform cubic B-spline using four neighboring control points."""
        pts = self._points
        n = len(pts)
        # Gather 4 control points (clamped at boundaries)
        i = seg_idx
        p = [pts[max(0, i - 1)], pts[i], pts[min(n - 1, i + 1)],
             pts[min(n - 1, i + 2)]]
        t2 = t * t
        t3 = t2 * t
        b0 = (1 - 3 * t + 3 * t2 - t3) / 6
        b1 = (4 - 6 * t2 + 3 * t3) / 6
        b2 = (1 + 3 * t + 3 * t2 - 3 * t3) / 6
        b3 = t3 / 6
        return float(b0 * p[0].y + b1 * p[1].y + b2 * p[2].y + b3 * p[3].y)

    # ------------------------------------------------------------------ #
    # Serialization                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {"points": [p.to_dict() for p in self._points]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SplineCurve:
        """Deserialize from a dict (as produced by :meth:`to_dict`)."""
        curve = cls.__new__(cls)
        curve._points = [SplinePoint.from_dict(
            p) for p in data.get("points", [])]
        if not curve._points:
            curve._points = [
                SplinePoint(0.0, 0.0, PointType.LINEAR),
                SplinePoint(1.0, 1.0, PointType.LINEAR),
            ]
        return curve

    def copy(self) -> SplineCurve:
        """Return a deep copy of this curve."""
        return SplineCurve.from_dict(self.to_dict())


__all__ = ["SplineCurve"]
