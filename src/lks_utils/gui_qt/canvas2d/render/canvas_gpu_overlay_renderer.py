"""GPU renderer for Canvas2D full-viewport overlays."""
from __future__ import annotations

from pathlib import Path
import time
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
from PySide6.QtGui import QColor
from lks_utils.gpu.gpu_timer_query import GpuTimerQuery, HAS_GPU_TIMER_QUERY
from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D
from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_axes_lines import (
        AxesLinesOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_canvas_border import (
        CanvasBorderOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_checkerboard import (
        CheckerboardOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_color_backdrop import ColorBackdrop
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_dot_grid import DotGridOverlay
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_home_grid import (
        HomeGridOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_texture_canvas import (
        TextureCanvasOverlay,
    )
    from lks_utils.gui_qt.canvas2d.canvas_objects.overlays.overlay_world_grid import WorldGridOverlay

try:
    import moderngl
    HAS_MODERNGL = True
except ImportError:
    HAS_MODERNGL = False

_SHADER_DIR = Path(__file__).resolve().parent.parent / "canvas_objects" / "overlays" / "shaders"
OverlayTimingEntry = tuple[str, float] | tuple[str, float, float]


def _load_shader(name: str) -> str:
    return (_SHADER_DIR / name).read_text(encoding="utf-8")


class Canvas2DGPUOverlayRenderer:
    """Render fullscreen Canvas2D overlays as ModernGL shader passes."""

    OverlayLayer = Literal["background", "foreground", "all"]

    def __init__(self, ctx: Any) -> None:
        if not HAS_MODERNGL:
            raise RuntimeError(
                "ModernGL is required for GPU Canvas2D overlays")
        self._ctx = ctx
        vertices = np.array(
            [-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype="f4")
        self._vbo = ctx.buffer(vertices.tobytes())
        vertex_shader = _load_shader("fullscreen_quad.vert")
        self._grid_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("dot_grid_overlay.frag"),
        )
        self._solid_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("solid_overlay.frag"),
        )
        self._world_grid_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("world_grid_overlay.frag"),
        )
        self._canvas_border_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("canvas_border_overlay.frag"),
        )
        self._texture_overlay_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("texture_canvas_overlay.frag"),
        )
        self._checkerboard_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("checkerboard_overlay.frag"),
        )
        self._axes_lines_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("axes_lines_overlay.frag"),
        )
        self._home_grid_program = ctx.program(
            vertex_shader=vertex_shader,
            fragment_shader=_load_shader("home_grid_overlay.frag"),
        )
        self._grid_vao = ctx.vertex_array(
            self._grid_program, [(self._vbo, "2f", "in_pos")])
        self._solid_vao = ctx.vertex_array(
            self._solid_program, [(self._vbo, "2f", "in_pos")])
        self._world_grid_vao = ctx.vertex_array(
            self._world_grid_program,
            [(self._vbo, "2f", "in_pos")],
        )
        self._canvas_border_vao = ctx.vertex_array(
            self._canvas_border_program,
            [(self._vbo, "2f", "in_pos")],
        )
        self._texture_overlay_vao = ctx.vertex_array(
            self._texture_overlay_program,
            [(self._vbo, "2f", "in_pos")],
        )
        self._checkerboard_vao = ctx.vertex_array(
            self._checkerboard_program,
            [(self._vbo, "2f", "in_pos")],
        )
        self._axes_lines_vao = ctx.vertex_array(
            self._axes_lines_program,
            [(self._vbo, "2f", "in_pos")],
        )
        self._home_grid_vao = ctx.vertex_array(
            self._home_grid_program,
            [(self._vbo, "2f", "in_pos")],
        )
        self._overlay_texture_cache: dict[int, tuple[int, Any]] = {}

    @staticmethod
    def is_gpu_overlay(overlay: object) -> bool:
        return isinstance(overlay, ViewportOverlay) and overlay.can_render_gpu()

    @staticmethod
    def _matches_layer(z_order: int, layer: OverlayLayer) -> bool:
        if layer == "background":
            return z_order < 0
        if layer == "foreground":
            return z_order >= 0
        return True

    def planned_consumed(self, scene: Scene2D, *, layer: OverlayLayer) -> set[int]:
        consumed: set[int] = set()
        for overlay in sorted(scene.overlays(), key=lambda obj: obj.z_order):
            if not isinstance(overlay, ViewportOverlay):
                continue
            if not overlay.can_render_gpu():
                continue
            if not self._matches_layer(overlay.z_order, layer):
                continue
            consumed.add(id(overlay))
        return consumed

    def render(
        self,
        scene: Scene2D,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float] | None = None,
        device_pixel_ratio: float = 1.0,
        *,
        layer: OverlayLayer = "background",
        timing_sink: list[OverlayTimingEntry] | None = None,
        gpu_timing: bool = False,
    ) -> set[int]:
        consumed: set[int] = set()
        ctx = self._ctx
        width, height = viewport_px
        logical_size = viewport_logical_px or (float(width), float(height))
        ctx.viewport = (0, 0, width, height)
        if layer == "background":
            bg = QColor(PALETTE["canvas_bg"])
            ctx.clear(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
        ctx.enable(ctx.BLEND)
        ctx.blend_func = (ctx.SRC_ALPHA, ctx.ONE_MINUS_SRC_ALPHA)

        for overlay in sorted(scene.overlays(), key=lambda obj: obj.z_order):
            if not isinstance(overlay, ViewportOverlay):
                continue
            if not overlay.can_render_gpu():
                continue
            if not self._matches_layer(overlay.z_order, layer):
                continue
            t0 = time.perf_counter()
            gpu_ms = 0.0
            if gpu_timing and HAS_GPU_TIMER_QUERY:
                with GpuTimerQuery(self._ctx) as tq:
                    overlay.render_gpu(
                        self,
                        view,
                        viewport_px,
                        logical_size,
                        device_pixel_ratio,
                    )
                gpu_ms = tq.elapsed_ms
            else:
                overlay.render_gpu(
                    self,
                    view,
                    viewport_px,
                    logical_size,
                    device_pixel_ratio,
                )
            if timing_sink is not None:
                duration_ms = (time.perf_counter() - t0) * 1000.0
                timing_sink.append(
                    (type(overlay).__name__, duration_ms, gpu_ms))
            consumed.add(id(overlay))
        ctx.disable(ctx.BLEND)
        return consumed

    def render_color_backdrop_overlay(self, overlay: ColorBackdrop) -> None:
        color = overlay.color
        program = self._solid_program
        program["u_color"].value = (
            color.redF(), color.greenF(), color.blueF(), color.alphaF())
        self._solid_vao.render(moderngl.TRIANGLE_STRIP)

    def render_dot_grid_overlay(
        self,
        overlay: DotGridOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        color = overlay.subdivision_dot_color
        strong = overlay.major_dot_color
        program = self._grid_program
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_size_logical"].value = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        program["u_dpr"].value = float(max(device_pixel_ratio, 1e-6))
        program["u_center"].value = (
            float(view.center_world[0]), float(view.center_world[1]))
        program["u_zoom"].value = float(view.zoom)
        program["u_rotation"].value = float(view.rotation_radians)
        program["u_grid_scale"].value = float(overlay.grid_scale)
        program["u_grid_space_scale"].value = float(overlay.grid_space_scale)
        program["u_subdivisions"].value = float(overlay.subdivisions)
        program["u_dot_radius_px"].value = float(overlay.dot_radius_px)
        program["u_dot_color"].value = (
            color.redF(), color.greenF(), color.blueF(), color.alphaF())
        program["u_major_color"].value = (
            strong.redF(), strong.greenF(), strong.blueF(), strong.alphaF())
        self._grid_vao.render(moderngl.TRIANGLE_STRIP)

    def render_world_grid_overlay(
        self,
        overlay: WorldGridOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        minor = QColor(PALETTE["dot_grid"])
        major = QColor(PALETTE["dot_grid_strong"])
        program = self._world_grid_program
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_size_logical"].value = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        program["u_dpr"].value = float(max(device_pixel_ratio, 1e-6))
        program["u_center"].value = (
            float(view.center_world[0]), float(view.center_world[1]))
        program["u_zoom"].value = float(view.zoom)
        program["u_rotation"].value = float(view.rotation_radians)
        program["u_grid_scale"].value = float(overlay.grid_scale)
        program["u_lod_base"].value = float(overlay.lod_base)
        program["u_minor_alpha"].value = float(overlay.minor_alpha)
        program["u_major_line_width_px"].value = float(overlay.line_width_px)
        program["u_minor_line_width_px"].value = float(
            overlay.minor_line_width_px)
        program["u_minor_color"].value = (
            minor.redF(), minor.greenF(), minor.blueF(), minor.alphaF())
        program["u_major_color"].value = (
            major.redF(), major.greenF(), major.blueF(), major.alphaF())
        self._world_grid_vao.render(moderngl.TRIANGLE_STRIP)

    def render_canvas_border_overlay(
        self,
        overlay: CanvasBorderOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        program = self._canvas_border_program
        aabb = overlay.world_aabb
        color = overlay.color
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_size_logical"].value = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        program["u_dpr"].value = float(max(device_pixel_ratio, 1e-6))
        program["u_center"].value = (
            float(view.center_world[0]), float(view.center_world[1]))
        program["u_zoom"].value = float(view.zoom)
        program["u_rotation"].value = float(view.rotation_radians)
        program["u_rect"].value = (
            float(aabb.x0),
            float(aabb.y0),
            float(aabb.x1),
            float(aabb.y1),
        )
        program["u_line_width_px"].value = float(overlay.line_width_px)
        program["u_border_color"].value = (
            color.redF(), color.greenF(), color.blueF(), color.alphaF())
        self._canvas_border_vao.render(moderngl.TRIANGLE_STRIP)

    def _texture_for_overlay(self, overlay: TextureCanvasOverlay) -> Any:
        overlay_id = id(overlay)
        revision = int(overlay.texture_revision)
        cached = self._overlay_texture_cache.get(overlay_id)
        if cached is not None and cached[0] == revision:
            return cached[1]

        if cached is not None:
            try:
                cached[1].release()
            except Exception:
                pass

        rgba = np.ascontiguousarray(
            np.flipud(overlay.prepared_texture_rgba8()))
        height, width, _ = rgba.shape
        texture = self._ctx.texture(
            (int(width), int(height)), 4, rgba.tobytes())
        texture.repeat_x = True
        texture.repeat_y = True
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self._overlay_texture_cache[overlay_id] = (revision, texture)
        return texture

    def render_texture_canvas_overlay(
        self,
        overlay: TextureCanvasOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        debug_color = overlay.debug_constant_color_rgba
        if debug_color is None:
            texture = self._texture_for_overlay(overlay)
            texture.use(location=0)
            width, height = texture.size
        else:
            width = height = 1
        dpr = float(max(device_pixel_ratio, 1e-6))
        inv_dpr = 1.0 / dpr
        scale = max(float(overlay.scale), 1e-6)
        inv_tile_size_px_x = scale / max(float(width), 1.0)
        inv_tile_size_px_y = scale / max(float(height), 1.0)
        rot = float(view.rotation_radians)
        c = float(np.cos(rot))
        s = float(np.sin(rot))
        anchor_physical_px = (
            float(view.center_world[0]) * float(view.zoom) * dpr,
            float(view.center_world[1]) * float(view.zoom) * dpr,
        )

        program = self._texture_overlay_program
        if debug_color is None:
            program["u_texture0"].value = 0
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_dpr"].value = dpr
        program["u_inv_dpr"].value = inv_dpr
        program["u_rot_cs"].value = (c, s)
        program["u_anchor_physical_px"].value = anchor_physical_px
        program["u_inv_tile_size_px"].value = (
            inv_tile_size_px_x,
            inv_tile_size_px_y,
        )
        program["u_opacity"].value = float(overlay.opacity)
        program["u_phase_offset_px"].value = (
            float(overlay.phase_offset_px[0]),
            float(overlay.phase_offset_px[1]),
        )
        program["u_debug_constant_enabled"].value = bool(
            debug_color is not None)
        program["u_debug_constant_color"].value = (
            debug_color if debug_color is not None else (0.0, 0.0, 0.0, 1.0)
        )

        # Some shader variants optimize out camera uniforms (e.g., pure
        # screen-space mapping). Keep these writes optional so both world- and
        # screen-space fragment shaders are supported by the same renderer path.
        try:
            program["u_size_logical"].value = (
                float(viewport_logical_px[0]),
                float(viewport_logical_px[1]),
            )
        except KeyError:
            pass
        self._texture_overlay_vao.render(moderngl.TRIANGLE_STRIP)
        # Qt's QPainter text path can inherit the last bound sampler/texture
        # from the raw GL pass on some drivers unless we clear it explicitly.
        self._ctx.clear_samplers()

    def render_checkerboard_overlay(
        self,
        overlay: CheckerboardOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        color_a = overlay.color_a
        color_b = overlay.color_b

        program = self._checkerboard_program
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_size_logical"].value = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        program["u_dpr"].value = float(max(device_pixel_ratio, 1e-6))
        program["u_center"].value = (
            float(view.center_world[0]), float(view.center_world[1]))
        program["u_zoom"].value = float(view.zoom)
        program["u_rotation"].value = float(view.rotation_radians)
        program["u_tile_size_px"].value = float(overlay.tile_size_px)
        program["u_scale"].value = float(overlay.scale)
        program["u_opacity"].value = float(overlay.opacity)
        program["u_color_a"].value = (
            color_a.redF(), color_a.greenF(), color_a.blueF(), color_a.alphaF())
        program["u_color_b"].value = (
            color_b.redF(), color_b.greenF(), color_b.blueF(), color_b.alphaF())
        self._checkerboard_vao.render(moderngl.TRIANGLE_STRIP)

    def render_axes_lines_overlay(
        self,
        overlay: AxesLinesOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        x_color = overlay.x_color
        y_color = overlay.y_color
        program = self._axes_lines_program
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_size_logical"].value = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        program["u_dpr"].value = float(max(device_pixel_ratio, 1e-6))
        program["u_center"].value = (
            float(view.center_world[0]), float(view.center_world[1]))
        program["u_zoom"].value = float(view.zoom)
        program["u_rotation"].value = float(view.rotation_radians)
        program["u_line_width_px"].value = float(overlay.line_width_px)
        program["u_x_color"].value = (
            x_color.redF(), x_color.greenF(), x_color.blueF(), x_color.alphaF())
        program["u_y_color"].value = (
            y_color.redF(), y_color.greenF(), y_color.blueF(), y_color.alphaF())
        self._axes_lines_vao.render(moderngl.TRIANGLE_STRIP)

    def render_home_grid_overlay(
        self,
        overlay: HomeGridOverlay,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        line_color = overlay.color
        border_color = overlay.border_color
        program = self._home_grid_program
        program["u_size_px"].value = (
            float(viewport_px[0]), float(viewport_px[1]))
        program["u_size_logical"].value = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        program["u_dpr"].value = float(max(device_pixel_ratio, 1e-6))
        program["u_center"].value = (
            float(view.center_world[0]), float(view.center_world[1]))
        program["u_zoom"].value = float(view.zoom)
        program["u_rotation"].value = float(view.rotation_radians)
        program["u_extent_world"].value = float(overlay.extent_world)
        program["u_step_world"].value = float(overlay.step_world)
        program["u_line_width_px"].value = float(overlay.line_thickness_px)
        program["u_border_width_px"].value = float(overlay.border_thickness_px)
        program["u_line_color"].value = (
            line_color.redF(), line_color.greenF(), line_color.blueF(), line_color.alphaF())
        program["u_border_color"].value = (
            border_color.redF(), border_color.greenF(), border_color.blueF(), border_color.alphaF())
        self._home_grid_vao.render(moderngl.TRIANGLE_STRIP)

    def release(self) -> None:
        for _, texture in self._overlay_texture_cache.values():
            try:
                texture.release()
            except Exception:
                pass
        self._overlay_texture_cache.clear()

        for resource in (
            self._grid_vao,
            self._solid_vao,
            self._world_grid_vao,
            self._canvas_border_vao,
            self._texture_overlay_vao,
            self._checkerboard_vao,
            self._axes_lines_vao,
            self._home_grid_vao,
            self._grid_program,
            self._solid_program,
            self._world_grid_program,
            self._canvas_border_program,
            self._texture_overlay_program,
            self._checkerboard_program,
            self._axes_lines_program,
            self._home_grid_program,
            self._vbo,
        ):
            try:
                resource.release()
            except Exception:
                pass


__all__ = ["Canvas2DGPUOverlayRenderer", "HAS_MODERNGL"]
