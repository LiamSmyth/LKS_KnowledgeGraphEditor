"""`ViewTransform`: immutable pan / zoom / rotation for a 2-D viewport.

The viewport is defined by:

* ``center_world`` — the world coordinate placed at the centre of the
  widget.
* ``zoom`` — screen pixels per world unit (1.0 = 1:1).
* ``rotation_radians`` — counter-clockwise rotation around the viewport
  centre.

All transforms are immutable value objects. Use ``with_*`` to derive
modified copies.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from lks_utils.spatial.aabb import AABB
from lks_utils.spatial.transform2d import Transform2D


@dataclass(frozen=True, slots=True)
class ViewTransform:
    """Immutable pan/zoom/rotation describing a 2-D viewport.

    Conventions:
        * World coordinates: cartesian, Y-up.
        * Screen coordinates: pixels, top-left origin, Y-down (Qt
          convention).
        * Rotation: counter-clockwise in radians around the viewport
          centre.
    """

    center_world: tuple[float, float] = (0.0, 0.0)
    zoom: float = 1.0
    rotation_radians: float = 0.0

    def __post_init__(self) -> None:
        if self.zoom <= 0.0:
            raise ValueError(f"zoom must be > 0, got {self.zoom}")

    @property
    def transform(self) -> Transform2D:
        """The camera-relative portion of the view as a :class:`~lks_utils.spatial.Transform2D`.

        The returned ``Transform2D`` encodes the rotation and zoom (scale)
        only — *not* the ``center_world`` translation, which is kept
        separate because it depends on the widget pixel size.

        Round-trip::

            vt = ViewTransform(center_world=(cx, cy), zoom=z, rotation_radians=r)
            t = vt.transform
            assert ViewTransform(vt.center_world, t.scale, t.rotation_radians) == vt
        """
        return Transform2D(
            translation=(0.0, 0.0),
            rotation_radians=self.rotation_radians,
            scale=self.zoom,
        )

    # ------------------------------------------------------------------ #
    # Coordinate transforms                                                #
    # ------------------------------------------------------------------ #

    def world_to_screen(
        self,
        world_pt: tuple[float, float],
        viewport_size_px: tuple[float, float],
    ) -> tuple[float, float]:
        """Map a world point to screen pixels (top-left origin, Y-down)."""
        wx, wy = world_pt
        cx, cy = self.center_world
        vw, vh = viewport_size_px
        # Translate so viewport centre is at origin.
        dx = wx - cx
        dy = wy - cy
        # Rotate (CCW in world-space).
        cos_r = math.cos(self.rotation_radians)
        sin_r = math.sin(self.rotation_radians)
        rx = cos_r * dx + sin_r * dy
        ry = -sin_r * dx + cos_r * dy
        # Scale.
        sx = rx * self.zoom
        sy = ry * self.zoom
        # World Y-up -> screen Y-down.
        return (vw / 2.0 + sx, vh / 2.0 - sy)

    def screen_to_world(
        self,
        screen_pt: tuple[float, float],
        viewport_size_px: tuple[float, float],
    ) -> tuple[float, float]:
        """Inverse of `world_to_screen`."""
        sx_px, sy_px = screen_pt
        vw, vh = viewport_size_px
        cx, cy = self.center_world
        # Centre on viewport.
        sx = sx_px - vw / 2.0
        sy = -(sy_px - vh / 2.0)  # screen Y-down -> world Y-up
        # Inverse scale.
        rx = sx / self.zoom
        ry = sy / self.zoom
        # Inverse rotate.
        cos_r = math.cos(self.rotation_radians)
        sin_r = math.sin(self.rotation_radians)
        wx = cos_r * rx - sin_r * ry
        wy = sin_r * rx + cos_r * ry
        return (wx + cx, wy + cy)

    def viewport_aabb_world(
        self, viewport_size_px: tuple[float, float]
    ) -> AABB:
        """The current viewport rectangle in world coordinates.

        When the viewport is rotated, returns the axis-aligned bounding
        box of the rotated viewport quad — useful for cull queries.
        """
        vw, vh = viewport_size_px
        corners = [
            self.screen_to_world((0.0, 0.0), viewport_size_px),
            self.screen_to_world((vw, 0.0), viewport_size_px),
            self.screen_to_world((vw, vh), viewport_size_px),
            self.screen_to_world((0.0, vh), viewport_size_px),
        ]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return AABB(min(xs), min(ys), max(xs), max(ys))

    def model_view_matrix_3x3(
        self, viewport_size_px: tuple[float, float]
    ) -> np.ndarray:
        """3x3 affine matrix M such that ``screen = M @ [wx, wy, 1]``.

        Useful for handing to a vertex shader that expects to multiply
        homogeneous world-space points.
        """
        vw, vh = viewport_size_px
        cos_r = math.cos(self.rotation_radians) * self.zoom
        sin_r = math.sin(self.rotation_radians) * self.zoom
        cx, cy = self.center_world
        # Compose: translate(-c) -> rotate -> scale -> flip Y -> translate(+vw/2, +vh/2)
        a = cos_r
        b = sin_r
        c = -sin_r
        d = cos_r
        # Note Y-flip baked in:
        m = np.array(
            [
                [a, b, vw / 2.0 - (a * cx + b * cy)],
                [-c, -d, vh / 2.0 - (-c * cx + -d * cy)],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        return m

    # ------------------------------------------------------------------ #
    # Immutable mutators                                                   #
    # ------------------------------------------------------------------ #

    def with_zoom(self, zoom: float) -> ViewTransform:
        return ViewTransform(self.center_world, float(zoom),
                             self.rotation_radians)

    def with_center(self, center: tuple[float, float]) -> ViewTransform:
        return ViewTransform(
            (float(center[0]), float(center[1])),
            self.zoom,
            self.rotation_radians,
        )

    def with_rotation(self, radians: float) -> ViewTransform:
        return ViewTransform(self.center_world, self.zoom, float(radians))

    def lerp(self, other: ViewTransform, t: float) -> ViewTransform:
        """Linear interpolation. ``t=0`` returns self, ``t=1`` returns other.

        Zoom is interpolated geometrically (so 1->4 at t=0.5 = 2, not 2.5)
        and rotation is interpolated along the shorter arc.
        """
        t = float(t)
        cx0, cy0 = self.center_world
        cx1, cy1 = other.center_world
        cx = cx0 + (cx1 - cx0) * t
        cy = cy0 + (cy1 - cy0) * t
        # Geometric zoom interpolation.
        zoom = self.zoom * (other.zoom / self.zoom) ** t
        # Shortest-arc rotation interpolation.
        delta = (other.rotation_radians -
                 self.rotation_radians) % (2 * math.pi)
        if delta > math.pi:
            delta -= 2 * math.pi
        rot = self.rotation_radians + delta * t
        return ViewTransform((cx, cy), zoom, rot)


__all__ = ["ViewTransform"]
