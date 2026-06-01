"""lks_utils.curve — shared spline curve system.

Provides a reusable monotonic-capable spline curve model for height remapping,
blend-mask falloffs, and any 0→1 mapping in displacement-map workflows.

Typical usage::

    from lks_utils.curve import SplineCurve, MonotonicSplineCurve, get_preset

    # Generic curve (may be non-monotonic)
    curve = SplineCurve()
    curve.add_point(0.3, 0.5)
    y = curve.evaluate(0.3)  # 0.5

    # Height-safe monotonic curve
    mcurve = MonotonicSplineCurve()
    mcurve.add_point(0.5, 0.6)
    lut = mcurve.to_lut(256)  # float32 array of 256 y samples

    # Built-in presets
    s = get_preset("s_curve")
"""
from __future__ import annotations

from lks_utils.curve.spline_point import PointType, SplinePoint, TangentMode
from lks_utils.curve.spline_curve import SplineCurve
from lks_utils.curve.monotonic_spline_curve import MonotonicSplineCurve, is_monotonic_dict
from lks_utils.curve.presets import (
    get_preset,
    PRESET_NAMES,
    linear,
    s_curve,
    ease_in,
    ease_out,
    bell,
    smoothstep,
    inverse,
)

__all__ = [
    # Data model
    "PointType",
    "TangentMode",
    "SplinePoint",
    "SplineCurve",
    "MonotonicSplineCurve",
    "is_monotonic_dict",
    # Presets
    "get_preset",
    "PRESET_NAMES",
    "linear",
    "s_curve",
    "ease_in",
    "ease_out",
    "bell",
    "smoothstep",
    "inverse",
]
