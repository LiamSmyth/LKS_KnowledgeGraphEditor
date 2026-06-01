"""SplinePoint — control point dataclass for spline curves."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PointType(str, Enum):
    """Interpolation mode for a spline control point.

    Determines how the curve segment *leaving* this point is computed.
    """

    LINEAR = "linear"
    """Straight line to the next point — C0 continuity only."""

    BEZIER = "bezier"
    """Cubic Bézier with explicit handle_in / handle_out tangents."""

    BSPLINE = "bspline"
    """Uniform cubic B-spline — automatically smooth, no explicit handles."""


class TangentMode(str, Enum):
    """Per-side tangent behavior for Bézier handles."""

    BROKEN = "broken"
    """This side is edited independently from the opposite side."""

    ALIGNED = "aligned"
    """This side mirrors angle with the opposite side, preserving opposite length."""

    AUTO = "auto"
    """This side mirrors the opposite side (opposite direction, same length)."""


@dataclass
class SplinePoint:
    """A single control point on a 2-D spline curve.

    All coordinates are normalized to the ``[0, 1]`` square.

    Attributes:
        x:          Horizontal position in ``[0, 1]``.
        y:          Vertical position in ``[0, 1]``.
        point_type: Interpolation mode leaving this point.
        handle_in:  Relative offset of the *incoming* Bézier tangent handle.
                    None for linear / B-spline points.
        handle_out: Relative offset of the *outgoing* Bézier tangent handle.
                    None for linear / B-spline points.
    """

    x: float
    y: float
    point_type: PointType = PointType.LINEAR
    handle_in: tuple[float, float] | None = None
    handle_out: tuple[float, float] | None = None
    tangent_in_mode: TangentMode = TangentMode.BROKEN
    tangent_out_mode: TangentMode = TangentMode.BROKEN

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (JSON-safe)."""
        data: dict[str, Any] = {
            "x": self.x,
            "y": self.y,
            "point_type": self.point_type.value,
        }
        if self.handle_in is not None:
            data["handle_in"] = list(self.handle_in)
        if self.handle_out is not None:
            data["handle_out"] = list(self.handle_out)
        data["tangent_in_mode"] = self.tangent_in_mode.value
        data["tangent_out_mode"] = self.tangent_out_mode.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SplinePoint:
        """Deserialize from a plain dict."""
        hi = data.get("handle_in")
        ho = data.get("handle_out")
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            point_type=PointType(
                data.get("point_type", PointType.LINEAR.value)),
            # type: ignore[arg-type]
            handle_in=tuple(hi) if hi is not None else None,
            # type: ignore[arg-type]
            handle_out=tuple(ho) if ho is not None else None,
            tangent_in_mode=TangentMode(
                data.get("tangent_in_mode", TangentMode.BROKEN.value)),
            tangent_out_mode=TangentMode(
                data.get("tangent_out_mode", TangentMode.BROKEN.value)),
        )


__all__ = ["PointType", "TangentMode", "SplinePoint"]
