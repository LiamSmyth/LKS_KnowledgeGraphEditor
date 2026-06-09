"""World-anchored tiled dot matrix overlay."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPaintEngine, QPainter, QTransform

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform

_LOD_BASE = 2.0
_TILE_LOGICAL_SIZE = 256.0
_CACHE_LIMIT = 128
_ROTATED_POINT_LIMIT = 30_000


def _parse_qcolor(value: QColor | str | None, fallback: str) -> QColor:
    if isinstance(value, QColor):
        color = QColor(value)
    elif isinstance(value, str):
        color = QColor(value)
    else:
        color = QColor(fallback)
    if not color.isValid():
        color = QColor(fallback)
    return color


def _qcolor_hex_argb(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexArgb)


@dataclass(frozen=True, slots=True)
class DotGridOverlayTheme:
    """Visual theme payload for dot-grid rendering."""

    major_dot_color: str = PALETTE["dot_grid_strong"]
    subdivision_dot_color: str = PALETTE["dot_grid"]
    dot_radius_px: float = 1.5

    def to_dict(self) -> dict[str, str | float]:
        return {
            "major_dot_color": self.major_dot_color,
            "subdivision_dot_color": self.subdivision_dot_color,
            "dot_radius_px": float(self.dot_radius_px),
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> DotGridOverlayTheme:
        if not isinstance(data, dict):
            return cls()
        return cls(
            major_dot_color=str(
                data.get("major_dot_color", PALETTE["dot_grid_strong"])
            ),
            subdivision_dot_color=str(
                data.get("subdivision_dot_color", PALETTE["dot_grid"])
            ),
            dot_radius_px=float(data.get("dot_radius_px", 1.5)),
        )


class DotGridOverlay(ViewportOverlay):
    """Infinite dot matrix drawn from world-anchored tiled cells.

    ``grid_scale`` is the major grid interval at 100% zoom in world units.
    Major dots land on integer multiples of the active grid scale, and
    subdivision dots split each cell into equal world-space intervals.
    """

    screen_space = False
    z_order = -1000
    supports_gpu_rendering = True

    def __init__(
        self,
        grid_scale: float = 1.0,
        grid_space_scale: float = 1.0,
        subdivisions: int = 3,
        dot_radius_px: float | None = None,
        subdivision_dot_color: QColor | str | None = None,
        major_dot_color: QColor | str | None = None,
        theme: DotGridOverlayTheme | None = None,
        subdivision_alpha: float | None = None,
    ) -> None:
        super().__init__()
        theme_cfg = theme or DotGridOverlayTheme()
        self.grid_scale = max(float(grid_scale), 1e-9)
        self.grid_space_scale = max(float(grid_space_scale), 1e-9)
        self.subdivisions = max(0, int(subdivisions))
        resolved_radius = (
            float(theme_cfg.dot_radius_px)
            if dot_radius_px is None
            else float(dot_radius_px)
        )
        self.dot_radius_px = max(resolved_radius, 0.1)
        self._subdivision_dot_color = _parse_qcolor(
            subdivision_dot_color,
            theme_cfg.subdivision_dot_color,
        )
        self._major_dot_color = _parse_qcolor(
            major_dot_color,
            theme_cfg.major_dot_color,
        )

        # Legacy compatibility: keep reading ``subdivision_alpha`` but fold
        # it into the subdivision color alpha channel.
        if subdivision_alpha is not None:
            scale = max(0.0, min(1.0, float(subdivision_alpha)))
            legacy_alpha = int(
                round(self._subdivision_dot_color.alpha() * scale))
            self._subdivision_dot_color.setAlpha(legacy_alpha)

        self._tile_image_cache: dict[tuple[int, ...], QImage] = {}

    @staticmethod
    def _smoothstep01(t: float) -> float:
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    @staticmethod
    def _scaled_alpha_u8(color: QColor, alpha_01: float) -> int:
        factor = max(0.0, min(1.0, alpha_01))
        return int(round(color.alpha() * factor))

    @staticmethod
    def _with_alpha_u8(color: QColor, alpha_u8: int) -> QColor:
        tinted = QColor(color)
        tinted.setAlpha(max(0, min(255, int(alpha_u8))))
        return tinted

    @property
    def subdivision_dot_color(self) -> QColor:
        return QColor(self._subdivision_dot_color)

    @property
    def major_dot_color(self) -> QColor:
        return QColor(self._major_dot_color)

    def visual_theme(self) -> DotGridOverlayTheme:
        return DotGridOverlayTheme(
            major_dot_color=_qcolor_hex_argb(self._major_dot_color),
            subdivision_dot_color=_qcolor_hex_argb(
                self._subdivision_dot_color),
            dot_radius_px=float(self.dot_radius_px),
        )

    def set_visual_theme(self, theme: DotGridOverlayTheme) -> None:
        self._major_dot_color = _parse_qcolor(
            theme.major_dot_color,
            PALETTE["dot_grid_strong"],
        )
        self._subdivision_dot_color = _parse_qcolor(
            theme.subdivision_dot_color,
            PALETTE["dot_grid"],
        )
        self.dot_radius_px = max(float(theme.dot_radius_px), 0.1)
        self._tile_image_cache.clear()

    @staticmethod
    def _wrap_phase(offset_px: float, period_px: float) -> float:
        if period_px <= 0.0:
            return 0.0
        wrapped = math.fmod(offset_px, period_px)
        if wrapped < 0.0:
            wrapped += period_px
        return wrapped

    @staticmethod
    def _device_pixel_ratio(ctx: CanvasPaintContext) -> float:
        dpr = max(ctx.device_pixel_ratio, 1.0)
        device = ctx.painter.device()
        getter = getattr(device, "devicePixelRatioF", None)
        if callable(getter):
            dpr = max(dpr, float(getter()))
        return dpr

    def _lod_pair_for_zoom(self, zoom: float) -> tuple[float, float, float, float]:
        log_zoom = math.log(max(zoom, 1e-9), _LOD_BASE)
        level = math.floor(log_zoom)
        blend = self._smoothstep01(log_zoom - level)
        base_step = self.grid_scale * self.grid_space_scale
        coarse_step = base_step / (_LOD_BASE**level)
        fine_step = coarse_step / _LOD_BASE
        return coarse_step, fine_step, 1.0 - blend, blend

    def _tile_cache_key(
        self,
        *,
        spacing_px: float,
        subdivision_rgb: tuple[int, int, int],
        major_rgb: tuple[int, int, int],
        coarse_sub_alpha_u8: int,
        coarse_major_alpha_u8: int,
        fine_sub_alpha_u8: int,
        fine_major_alpha_u8: int,
        dpr: float,
    ) -> tuple[int, ...]:
        spacing_milli_px = max(1, int(round(spacing_px * 1000.0)))
        radius_milli_px = max(1, int(round(self.dot_radius_px * 1000.0)))
        dpr_milli = max(1, int(round(dpr * 1000.0)))
        return (
            spacing_milli_px,
            self.subdivisions,
            int(subdivision_rgb[0]),
            int(subdivision_rgb[1]),
            int(subdivision_rgb[2]),
            int(major_rgb[0]),
            int(major_rgb[1]),
            int(major_rgb[2]),
            int(coarse_sub_alpha_u8),
            int(coarse_major_alpha_u8),
            int(fine_sub_alpha_u8),
            int(fine_major_alpha_u8),
            radius_milli_px,
            dpr_milli,
        )

    @staticmethod
    def _draw_wrapped_dot(
        painter: QPainter,
        x: float,
        y: float,
        radius: float,
        tile_extent: float,
    ) -> None:
        for dx in (-tile_extent, 0.0, tile_extent):
            for dy in (-tile_extent, 0.0, tile_extent):
                painter.drawEllipse(QPointF(x + dx, y + dy), radius, radius)

    def _cached_tile_image(
        self,
        *,
        spacing_px: float,
        subdivision_rgb: tuple[int, int, int],
        major_rgb: tuple[int, int, int],
        coarse_sub_alpha_u8: int,
        coarse_major_alpha_u8: int,
        fine_sub_alpha_u8: int,
        fine_major_alpha_u8: int,
        dpr: float,
    ) -> QImage:
        key = self._tile_cache_key(
            spacing_px=spacing_px,
            subdivision_rgb=subdivision_rgb,
            major_rgb=major_rgb,
            coarse_sub_alpha_u8=coarse_sub_alpha_u8,
            coarse_major_alpha_u8=coarse_major_alpha_u8,
            fine_sub_alpha_u8=fine_sub_alpha_u8,
            fine_major_alpha_u8=fine_major_alpha_u8,
            dpr=dpr,
        )
        cached = self._tile_image_cache.get(key)
        if cached is not None:
            return cached

        device_size = max(2, int(round(_TILE_LOGICAL_SIZE * dpr)))
        tile = QImage(
            device_size,
            device_size,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        tile.setDevicePixelRatio(dpr)
        tile.fill(Qt.GlobalColor.transparent)

        scale = max(spacing_px / _TILE_LOGICAL_SIZE, 1e-9)
        dot_radius = self.dot_radius_px / scale
        painter = QPainter(tile)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        self._paint_tile_level(
            painter,
            tile_extent=_TILE_LOGICAL_SIZE,
            subdivision_rgb=subdivision_rgb,
            major_rgb=major_rgb,
            sub_alpha_u8=coarse_sub_alpha_u8,
            major_alpha_u8=coarse_major_alpha_u8,
            dot_radius=dot_radius,
        )
        self._paint_tile_level(
            painter,
            tile_extent=_TILE_LOGICAL_SIZE / _LOD_BASE,
            subdivision_rgb=subdivision_rgb,
            major_rgb=major_rgb,
            sub_alpha_u8=fine_sub_alpha_u8,
            major_alpha_u8=fine_major_alpha_u8,
            dot_radius=dot_radius,
        )

        painter.end()
        if len(self._tile_image_cache) > _CACHE_LIMIT:
            self._tile_image_cache.clear()
        self._tile_image_cache[key] = tile
        return tile

    def _paint_tile_level(
        self,
        painter: QPainter,
        *,
        tile_extent: float,
        subdivision_rgb: tuple[int, int, int],
        major_rgb: tuple[int, int, int],
        sub_alpha_u8: int,
        major_alpha_u8: int,
        dot_radius: float,
    ) -> None:
        cells = self.subdivisions + 1
        if cells > 1 and sub_alpha_u8 > 0:
            painter.setBrush(
                QColor(
                    int(subdivision_rgb[0]),
                    int(subdivision_rgb[1]),
                    int(subdivision_rgb[2]),
                    sub_alpha_u8,
                )
            )
            repeats = max(1, int(round(_TILE_LOGICAL_SIZE / tile_extent)))
            for repeat_y in range(repeats):
                base_y = repeat_y * tile_extent
                for repeat_x in range(repeats):
                    base_x = repeat_x * tile_extent
                    for row in range(cells):
                        y = base_y + row * tile_extent / cells
                        for col in range(cells):
                            x = base_x + col * tile_extent / cells
                            self._draw_wrapped_dot(
                                painter,
                                x,
                                y,
                                dot_radius,
                                _TILE_LOGICAL_SIZE,
                            )

        if major_alpha_u8 > 0:
            painter.setBrush(
                QColor(
                    int(major_rgb[0]),
                    int(major_rgb[1]),
                    int(major_rgb[2]),
                    major_alpha_u8,
                )
            )
            repeats = max(1, int(round(_TILE_LOGICAL_SIZE / tile_extent)))
            for repeat_y in range(repeats):
                y = repeat_y * tile_extent
                for repeat_x in range(repeats):
                    x = repeat_x * tile_extent
                    self._draw_wrapped_dot(
                        painter,
                        x,
                        y,
                        dot_radius * 1.25,
                        _TILE_LOGICAL_SIZE,
                    )

    def _paint_pair_tiled(
        self,
        ctx: CanvasPaintContext,
        *,
        coarse_step: float,
        fine_step: float,
        coarse_alpha: float,
        fine_alpha: float,
    ) -> bool:
        # QOpenGL-backed paint engines can exhibit tile corruption artifacts for
        # drawTiled/brush paths; use a point/ellipse fallback there.
        engine = ctx.painter.paintEngine()
        if engine is not None and engine.type() in {
            QPaintEngine.Type.OpenGL,
            QPaintEngine.Type.OpenGL2,
        }:
            return False

        if coarse_alpha <= 0.01 and fine_alpha <= 0.01:
            return True

        del fine_step
        spacing_px = coarse_step * ctx.view.zoom
        if spacing_px <= 0.0:
            return False

        dpr = self._device_pixel_ratio(ctx)
        subdivision_rgb = (
            self._subdivision_dot_color.red(),
            self._subdivision_dot_color.green(),
            self._subdivision_dot_color.blue(),
        )
        major_rgb = (
            self._major_dot_color.red(),
            self._major_dot_color.green(),
            self._major_dot_color.blue(),
        )
        coarse_sub_alpha_u8 = (
            self._scaled_alpha_u8(self._subdivision_dot_color, coarse_alpha)
            if self.subdivisions > 0
            else 0
        )
        fine_sub_alpha_u8 = (
            self._scaled_alpha_u8(self._subdivision_dot_color, fine_alpha)
            if self.subdivisions > 0
            else 0
        )
        tile = self._cached_tile_image(
            spacing_px=spacing_px,
            subdivision_rgb=subdivision_rgb,
            major_rgb=major_rgb,
            coarse_sub_alpha_u8=coarse_sub_alpha_u8,
            coarse_major_alpha_u8=self._scaled_alpha_u8(
                self._major_dot_color, coarse_alpha
            ),
            fine_sub_alpha_u8=fine_sub_alpha_u8,
            fine_major_alpha_u8=self._scaled_alpha_u8(
                self._major_dot_color, fine_alpha
            ),
            dpr=dpr,
        )

        origin_x, origin_y = ctx.view.world_to_screen(
            (0.0, 0.0), ctx.viewport_size_px)
        rot = float(ctx.view.rotation_radians)
        if abs(rot) > 1e-8:
            # For a rotated view, the dot grid's repeat lattice is rotated in
            # screen space and can't be wrapped along screen axes — use the
            # full (unclipped) screen origin so the brush origin is exact.
            phase_x = origin_x
            phase_y = origin_y
        else:
            phase_x = self._wrap_phase(origin_x, spacing_px)
            phase_y = self._wrap_phase(origin_y, spacing_px)
        viewport_w, viewport_h = ctx.viewport_size_px
        brush = QBrush(tile)
        transform = QTransform()
        transform.scale(spacing_px / _TILE_LOGICAL_SIZE,
                        spacing_px / _TILE_LOGICAL_SIZE)
        if abs(rot) > 1e-8:
            # Rotate the brush pattern to align with the world grid axes in
            # screen space.  world_to_screen maps world +X to screen direction
            # (cos θ, sin θ), so rotating the brush clockwise by θ degrees
            # (Qt convention: positive = CW in Y-down screen space) aligns tile
            # columns with the visible world-X axis.
            transform.rotate(math.degrees(rot))
        brush.setTransform(transform)

        painter = ctx.painter
        painter.save()
        painter.resetTransform()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrushOrigin(QPointF(phase_x, phase_y))
        painter.fillRect(QRectF(0.0, 0.0, viewport_w, viewport_h), brush)
        painter.restore()
        return True

    def _bounds_for_step(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        step: float,
    ) -> tuple[int, int, int, int]:
        i_min = int(math.floor(x0 / step)) - 1
        i_max = int(math.ceil(x1 / step)) + 1
        j_min = int(math.floor(y0 / step)) - 1
        j_max = int(math.ceil(y1 / step)) + 1
        return i_min, i_max, j_min, j_max

    @staticmethod
    def _dot_count(bounds: tuple[int, int, int, int]) -> int:
        i_min, i_max, j_min, j_max = bounds
        return max(0, i_max - i_min + 1) * max(0, j_max - j_min + 1)

    def _paint_level_points(
        self,
        ctx: CanvasPaintContext,
        *,
        step: float,
        sub_alpha: float,
        major_alpha: float,
    ) -> None:
        cells = self.subdivisions + 1
        sub_step = step / cells
        aabb = ctx.viewport_aabb_world
        major_bounds = self._bounds_for_step(
            aabb.x0, aabb.y0, aabb.x1, aabb.y1, step)
        if self._dot_count(major_bounds) > _ROTATED_POINT_LIMIT:
            return

        painter = ctx.painter
        engine = painter.paintEngine()
        gl_engine = engine is not None and engine.type() in {
            QPaintEngine.Type.OpenGL,
            QPaintEngine.Type.OpenGL2,
        }

        world_dot_r = self.dot_radius_px / max(ctx.view.zoom, 1e-9)
        world_major_r = world_dot_r * 1.25

        def _draw_ellipse_points(
            points: list[QPointF],
            color: QColor,
            radius_world: float,
        ) -> None:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            for pt in points:
                painter.drawEllipse(pt, radius_world, radius_world)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        if cells > 1 and sub_alpha > 0.01:
            sub_bounds = self._bounds_for_step(
                aabb.x0, aabb.y0, aabb.x1, aabb.y1, sub_step)
            if self._dot_count(sub_bounds) <= _ROTATED_POINT_LIMIT:
                si_min, si_max, sj_min, sj_max = sub_bounds
                sub_color = self._with_alpha_u8(
                    self._subdivision_dot_color,
                    self._scaled_alpha_u8(
                        self._subdivision_dot_color, sub_alpha),
                )
                painter.setPen(
                    sub_color
                )
                points = [
                    QPointF(si * sub_step, sj * sub_step)
                    for sj in range(sj_min, sj_max + 1)
                    for si in range(si_min, si_max + 1)
                ]
                if gl_engine:
                    _draw_ellipse_points(points, sub_color, world_dot_r)
                else:
                    painter.drawPoints(points)

        if major_alpha > 0.01:
            mi_min, mi_max, mj_min, mj_max = major_bounds
            major_color = self._with_alpha_u8(
                self._major_dot_color,
                self._scaled_alpha_u8(self._major_dot_color, major_alpha),
            )
            painter.setPen(
                major_color
            )
            points = [
                QPointF(mi * step, mj * step)
                for mj in range(mj_min, mj_max + 1)
                for mi in range(mi_min, mi_max + 1)
            ]
            if gl_engine:
                _draw_ellipse_points(points, major_color, world_major_r)
            else:
                painter.drawPoints(points)

    def _paint_level(
        self,
        ctx: CanvasPaintContext,
        *,
        step: float,
        sub_alpha: float,
        major_alpha: float,
    ) -> None:
        self._paint_level_points(
            ctx, step=step, sub_alpha=sub_alpha, major_alpha=major_alpha)

    def paint(self, ctx: CanvasPaintContext) -> None:
        coarse_step, fine_step, coarse_alpha, fine_alpha = self._lod_pair_for_zoom(
            ctx.view.zoom)
        if self._paint_pair_tiled(
            ctx,
            coarse_step=coarse_step,
            fine_step=fine_step,
            coarse_alpha=coarse_alpha,
            fine_alpha=fine_alpha,
        ):
            return
        self._paint_level(
            ctx,
            step=coarse_step,
            sub_alpha=coarse_alpha,
            major_alpha=coarse_alpha,
        )
        self._paint_level(
            ctx,
            step=fine_step,
            sub_alpha=fine_alpha,
            major_alpha=fine_alpha,
        )

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        renderer.render_dot_grid_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    def to_dict(self) -> dict:
        theme = self.visual_theme()
        return {
            "type": "canvas2d.overlays.dot_grid",
            "grid_scale": self.grid_scale,
            "grid_space_scale": self.grid_space_scale,
            "subdivisions": self.subdivisions,
            "dot_radius_px": self.dot_radius_px,
            "subdivision_dot_color": theme.subdivision_dot_color,
            "major_dot_color": theme.major_dot_color,
            "theme": theme.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> DotGridOverlay:
        grid_scale = float(d.get("grid_scale", d.get("world_spacing", 1.0)))
        theme = DotGridOverlayTheme.from_dict(d.get("theme"))

        # Legacy compatibility: optional float multiplier for subdivision alpha.
        legacy_sub_alpha = d.get("subdivision_alpha")
        return cls(
            grid_scale=grid_scale,
            grid_space_scale=float(d.get("grid_space_scale", 1.0)),
            subdivisions=int(d.get("subdivisions", 1)),
            dot_radius_px=float(d.get("dot_radius_px", 1.5)),
            subdivision_dot_color=d.get(
                "subdivision_dot_color",
                theme.subdivision_dot_color,
            ),
            major_dot_color=d.get("major_dot_color", theme.major_dot_color),
            theme=theme,
            subdivision_alpha=(
                float(legacy_sub_alpha) if legacy_sub_alpha is not None else None
            ),
        )


__all__ = ["DotGridOverlay", "DotGridOverlayTheme"]
