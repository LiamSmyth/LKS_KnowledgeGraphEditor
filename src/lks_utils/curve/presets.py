"""Built-in curve presets for the lks_utils curve system.

Each factory function returns a ready-to-use :class:`~lks_utils.curve.spline_curve.SplineCurve`
populated with control points that approximate the named shape.
"""
from __future__ import annotations

from lks_utils.curve.spline_curve import SplineCurve
from lks_utils.curve.monotonic_spline_curve import MonotonicSplineCurve
from lks_utils.curve.spline_point import PointType


def _set_all_segments_type(curve: SplineCurve, point_type: PointType) -> None:
    """Set interpolation type on every left endpoint of each segment."""
    for i in range(max(0, len(curve.points) - 1)):
        curve.set_point_type(i, point_type)


def linear() -> SplineCurve:
    """Identity — straight diagonal from (0,0) to (1,1)."""
    return SplineCurve()


def s_curve() -> MonotonicSplineCurve:
    """S-curve — expands mid-tone contrast.

    Shadows pushed down, highlights pushed up.
    """
    c = MonotonicSplineCurve()
    c.add_point(0.25, 0.1)
    c.add_point(0.75, 0.9)
    _set_all_segments_type(c, PointType.BEZIER)
    return c


def ease_in() -> MonotonicSplineCurve:
    """Ease-in — slow start, fast finish (accelerating curve)."""
    c = MonotonicSplineCurve()
    c.add_point(0.5, 0.2)
    _set_all_segments_type(c, PointType.BEZIER)
    return c


def ease_out() -> MonotonicSplineCurve:
    """Ease-out — fast start, slow finish (decelerating curve)."""
    c = MonotonicSplineCurve()
    c.add_point(0.5, 0.8)
    _set_all_segments_type(c, PointType.BEZIER)
    return c


def bell() -> SplineCurve:
    """Bell / arch — rises to a mid-peak and falls back.

    Not monotonic — useful for falloff masks, not for height remapping.
    """
    c = SplineCurve()
    c._points[0].point_type  # just make sure it's initialized
    c.add_point(0.1, 0.0)
    c.add_point(0.5, 1.0)
    c.add_point(0.9, 0.0)
    # Override endpoints to y=0
    from lks_utils.curve.spline_point import SplinePoint
    c._points[0] = SplinePoint(0.0, 0.0, PointType.LINEAR)
    c._points[-1] = SplinePoint(1.0, 0.0, PointType.LINEAR)
    _set_all_segments_type(c, PointType.BSPLINE)
    return c


def smoothstep() -> MonotonicSplineCurve:
    """Smooth-step — cubic-smooth S from (0,0) to (1,1)."""
    c = MonotonicSplineCurve()
    c.add_point(0.25, 0.1)
    c.add_point(0.5, 0.5)
    c.add_point(0.75, 0.9)
    _set_all_segments_type(c, PointType.BEZIER)
    return c


def inverse() -> MonotonicSplineCurve:
    """Inverse — strong falloff, maps high values to low.

    Monotonically *decreasing* (flipped linear).
    """
    c = MonotonicSplineCurve()
    # Override endpoints
    from lks_utils.curve.spline_point import SplinePoint
    c._points[0] = SplinePoint(0.0, 1.0, PointType.LINEAR)
    c._points[-1] = SplinePoint(1.0, 0.0, PointType.LINEAR)
    return c


# Preset registry for programmatic access
PRESETS: dict[str, type[SplineCurve] | None] = {
    "linear": None,
    "s_curve": None,
    "ease_in": None,
    "ease_out": None,
    "bell": None,
    "smoothstep": None,
    "inverse": None,
}

_PRESET_FACTORIES = {
    "linear": linear,
    "s_curve": s_curve,
    "ease_in": ease_in,
    "ease_out": ease_out,
    "bell": bell,
    "smoothstep": smoothstep,
    "inverse": inverse,
}


def get_preset(name: str) -> SplineCurve:
    """Return a new curve instance for a named preset.

    Args:
        name: One of ``"linear"``, ``"s_curve"``, ``"ease_in"``, ``"ease_out"``,
              ``"bell"``, ``"smoothstep"``, ``"inverse"``.

    Returns:
        A fresh :class:`SplineCurve` (or subclass) instance.

    Raises:
        KeyError: If the preset name is not recognized.
    """
    factory = _PRESET_FACTORIES.get(name)
    if factory is None:
        msg = f"Unknown curve preset: {name!r}. Available: {list(_PRESET_FACTORIES)}"
        raise KeyError(msg)
    return factory()


PRESET_NAMES: tuple[str, ...] = tuple(_PRESET_FACTORIES.keys())

__all__ = [
    "linear",
    "s_curve",
    "ease_in",
    "ease_out",
    "bell",
    "smoothstep",
    "inverse",
    "get_preset",
    "PRESET_NAMES",
]
