"""`Transform2D`: immutable 2-D similarity transform (translate + rotate + uniform scale).

Encodes a TRS transform:

    T(p) = translation + scale * R(rotation_radians) * p

where ``R(r)`` is the standard CCW rotation matrix::

    R(r) = [[cos r, -sin r],
            [sin r,  cos r]]

All transforms are *frozen* (immutable) value objects.  Use the
:meth:`compose` / :meth:`inverse` algebra to build compound transforms,
and :meth:`lerp` for animation.

Relationship to ``ViewTransform``
----------------------------------
``ViewTransform`` stores its view state as ``(center_world, zoom,
rotation_radians)``.  Its ``.transform`` property exposes the
*camera-relative* portion as a ``Transform2D`` with
``translation=(0,0)``, ``rotation_radians=rotation_radians``,
``scale=zoom``.  The viewport centering offset is kept separate because
it depends on the widget pixel size.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.spatial.oriented_rect import OrientedRect


@dataclass(frozen=True, slots=True)
class Transform2D:
    """Immutable 2-D similarity transform: translate + rotate + uniform scale.

    The transform is applied as::

        T(p) = translation + scale * R(rotation_radians) * p

    Attributes:
        translation:       (tx, ty) in world units.
        rotation_radians:  CCW angle around the origin.
        scale:             Uniform scale factor (must be > 0).
    """

    translation: tuple[float, float] = (0.0, 0.0)
    rotation_radians: float = 0.0
    scale: float = 1.0

    # ------------------------------------------------------------------ #
    # Class-method constructors                                            #
    # ------------------------------------------------------------------ #

    @classmethod
    def identity(cls) -> Transform2D:
        """Return the identity transform."""
        return cls()

    @classmethod
    def from_translation(cls, t: tuple[float, float]) -> Transform2D:
        """Construct a pure-translation transform."""
        return cls(translation=(float(t[0]), float(t[1])))

    @classmethod
    def from_rotation(cls, r: float) -> Transform2D:
        """Construct a pure-rotation transform (CCW radians)."""
        return cls(rotation_radians=float(r))

    @classmethod
    def from_uniform_scale(cls, s: float) -> Transform2D:
        """Construct a pure-scale transform."""
        return cls(scale=float(s))

    @classmethod
    def from_components(
        cls,
        t: tuple[float, float],
        r: float,
        s: float,
    ) -> Transform2D:
        """Construct from translation, rotation (radians), and scale."""
        return cls(
            translation=(float(t[0]), float(t[1])),
            rotation_radians=float(r),
            scale=float(s),
        )

    # ------------------------------------------------------------------ #
    # Core application                                                     #
    # ------------------------------------------------------------------ #

    def apply_point(self, p: tuple[float, float]) -> tuple[float, float]:
        """Apply this transform to a 2-D point.

        Returns ``translation + scale * R(rotation_radians) * p``.
        """
        px, py = p
        tx, ty = self.translation
        cos_r = math.cos(self.rotation_radians)
        sin_r = math.sin(self.rotation_radians)
        x = tx + self.scale * (cos_r * px - sin_r * py)
        y = ty + self.scale * (sin_r * px + cos_r * py)
        return (x, y)

    def apply_aabb(self, aabb: AABB) -> AABB:
        """Apply this transform to an AABB.

        Returns the axis-aligned bounding box of the four transformed
        corners — which is what you want for culling queries even when
        the transform includes rotation.
        """
        corners = (
            self.apply_point((aabb.x0, aabb.y0)),
            self.apply_point((aabb.x1, aabb.y0)),
            self.apply_point((aabb.x1, aabb.y1)),
            self.apply_point((aabb.x0, aabb.y1)),
        )
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        return AABB(min(xs), min(ys), max(xs), max(ys))

    def apply_oriented(self, oc: OrientedRect) -> OrientedRect:
        """Apply this transform to an :class:`OrientedRect`.

        Transforms the centre point, scales the half-extents, and adds
        the rotation to the rect's own orientation.
        """
        # Lazy import to avoid circular dependency at module load time.
        from lks_utils.spatial.oriented_rect import OrientedRect as _OR  # noqa: PLC0415

        new_centre = self.apply_point(oc.centre)
        new_half = (oc.half_extents[0] * self.scale,
                    oc.half_extents[1] * self.scale)
        new_rot = oc.rotation_radians + self.rotation_radians
        return _OR(centre=new_centre, half_extents=new_half, rotation_radians=new_rot)

    # ------------------------------------------------------------------ #
    # Algebra                                                              #
    # ------------------------------------------------------------------ #

    def compose(self, other: Transform2D) -> Transform2D:
        """Return the composition ``self ∘ other`` (apply *other* first, then *self*).

        Equivalently: ``(self.compose(other)).apply_point(p) == self.apply_point(other.apply_point(p))``.

        Math::

            t_new = self.t + self.s * R(self.r) * other.t
            r_new = self.r + other.r
            s_new = self.s * other.s
        """
        tx_s, ty_s = self.translation
        tx_o, ty_o = other.translation
        cos_r = math.cos(self.rotation_radians)
        sin_r = math.sin(self.rotation_radians)
        # Apply self's rotation+scale to other's translation offset.
        new_tx = tx_s + self.scale * (cos_r * tx_o - sin_r * ty_o)
        new_ty = ty_s + self.scale * (sin_r * tx_o + cos_r * ty_o)
        return Transform2D(
            translation=(new_tx, new_ty),
            rotation_radians=self.rotation_radians + other.rotation_radians,
            scale=self.scale * other.scale,
        )

    def inverse(self) -> Transform2D:
        """Return the inverse transform ``T⁻¹`` such that ``T.compose(T.inverse()) ≈ identity``.

        Math (solving ``T(T_inv(q)) = q``)::

            T_inv(q) = R(-r) * (q - t) / s

        As a ``Transform2D``::

            t_inv = R(-r) * (-t) / s
            r_inv = -r
            s_inv = 1 / s
        """
        s = self.scale if abs(self.scale) > 1e-12 else 1e-12
        cos_r = math.cos(-self.rotation_radians)
        sin_r = math.sin(-self.rotation_radians)
        tx, ty = self.translation
        inv_tx = (cos_r * (-tx) - sin_r * (-ty)) / s
        inv_ty = (sin_r * (-tx) + cos_r * (-ty)) / s
        return Transform2D(
            translation=(inv_tx, inv_ty),
            rotation_radians=-self.rotation_radians,
            scale=1.0 / s,
        )

    def lerp(self, other: Transform2D, t: float) -> Transform2D:
        """Linearly interpolate toward *other*.

        ``t=0`` returns ``self``, ``t=1`` returns ``other``.

        * Translation: linear.
        * Scale: geometric (log-space) so that ``1→4`` at ``t=0.5`` gives ``2``.
        * Rotation: shortest arc.
        """
        t = float(t)
        tx0, ty0 = self.translation
        tx1, ty1 = other.translation
        tx = tx0 + (tx1 - tx0) * t
        ty = ty0 + (ty1 - ty0) * t
        # Geometric scale interpolation.
        s0 = max(abs(self.scale), 1e-12)
        scale = s0 * (other.scale / s0) ** t
        # Shortest-arc rotation.
        delta = (other.rotation_radians -
                 self.rotation_radians) % (2 * math.pi)
        if delta > math.pi:
            delta -= 2 * math.pi
        rot = self.rotation_radians + delta * t
        return Transform2D(translation=(tx, ty), rotation_radians=rot, scale=scale)


__all__ = ["Transform2D"]
