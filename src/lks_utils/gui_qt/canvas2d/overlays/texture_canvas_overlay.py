"""Texture-backed Canvas2D overlay with pivot-pinned world mapping."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QImage, QPainter, QTransform

from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.viewport_overlay import ViewportOverlay

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform


class TextureCanvasOverlay(ViewportOverlay):
    """Tile a texture across the viewport with world alignment and pinning.

    The base mapping is world-aligned (panning follows the page and rotation
    rotates the texture with the canvas). A dynamic phase offset is adjusted
    from interaction pivots (zoom-wheel position, rotate anchor, etc.) so the
    texel under that pivot remains visually pinned during camera changes while
    tile size stays screen-constant.
    """

    screen_space = True
    z_order = -1000
    supports_gpu_rendering = True

    def __init__(
        self,
        texture: QImage | np.ndarray | None = None,
        *,
        scale: float = 1.0,
        opacity: float = 1.0,
        max_texture_dim_px: int = 2048,
        enforce_power_of_two: bool = False,
    ) -> None:
        super().__init__()
        self.scale = max(float(scale), 1e-6)
        self.opacity = max(0.0, min(1.0, float(opacity)))
        self.max_texture_dim_px = max(1, int(max_texture_dim_px))
        self.enforce_power_of_two = bool(enforce_power_of_two)

        source = texture if texture is not None else self._default_noise_texture()
        self._source_rgba8 = self._coerce_to_rgba8(source)
        self._prepared_rgba8 = self._preprocess_rgba8(self._source_rgba8)

        self._cpu_texture_image_cache: dict[tuple[int, int], QImage] = {}
        self._texture_revision = 0
        self._phase_offset_px: tuple[float, float] = (0.0, 0.0)
        self._last_view: ViewTransform | None = None
        self._pivot_screen_px: tuple[float, float] | None = None
        self._pivot_locked: bool = False
        self._pin_view_changes: bool = True
        self._lock_reference_view: ViewTransform | None = None
        self._lock_reference_phase_offset_px: tuple[float, float] = (0.0, 0.0)
        self._lock_tex_coord_at_pivot: tuple[float, float] | None = None
        self._lock_viewport_logical_px: tuple[float, float] = (1.0, 1.0)
        self._lock_dpr: float = 1.0
        self._last_viewport_logical_px: tuple[float, float] = (1.0, 1.0)
        self._last_dpr: float = 1.0
        self._has_gpu_context: bool = False
        self._gl_safe_gpu_fallback: bool = True
        self._debug_constant_color_rgba: tuple[float,
                                               float, float, float] | None = None

    @property
    def texture_revision(self) -> int:
        return self._texture_revision

    def prepared_texture_rgba8(self) -> np.ndarray:
        return self._prepared_rgba8

    def set_gpu_enabled(self, enabled: bool) -> None:
        # Reset interaction-lock state when switching backend paths so
        # CPU and GPU modes start from a clean phase mapping.
        super().set_gpu_enabled(enabled)
        self.clear_interaction_pivot_lock()
        self._last_view = None
        self._phase_offset_px = (0.0, 0.0)

    def on_gpu_context_changed(self, gpu) -> None:  # noqa: ANN001
        self._has_gpu_context = gpu is not None

    def can_render_gpu(self) -> bool:
        if self.gpu_enabled:
            return True
        # QPainter CPU composition into QOpenGLWidget has proven unstable
        # for this overlay on some drivers/platforms; keep rendering on the
        # GPU path while attached to a GL canvas.
        return self._gl_safe_gpu_fallback and self._has_gpu_context

    @property
    def phase_offset_px(self) -> tuple[float, float]:
        return self._phase_offset_px

    @property
    def debug_constant_color_rgba(self) -> tuple[float, float, float, float] | None:
        return self._debug_constant_color_rgba

    def set_debug_constant_color_rgba(
        self,
        color: tuple[float, float, float, float] | None,
    ) -> None:
        if color is None:
            self._debug_constant_color_rgba = None
        else:
            r, g, b, a = color
            self._debug_constant_color_rgba = (
                max(0.0, min(1.0, float(r))),
                max(0.0, min(1.0, float(g))),
                max(0.0, min(1.0, float(b))),
                max(0.0, min(1.0, float(a))),
            )
        self.request_repaint()

    def set_interaction_pivot_screen(
        self,
        screen_pos: tuple[float, float],
        *,
        lock: bool = False,
        pin_view_changes: bool = True,
        view: ViewTransform | None = None,
        viewport_logical_px: tuple[float, float] | None = None,
        device_pixel_ratio: float | None = None,
    ) -> None:
        self._pin_view_changes = bool(pin_view_changes)
        if viewport_logical_px is not None:
            self._last_viewport_logical_px = (
                float(viewport_logical_px[0]),
                float(viewport_logical_px[1]),
            )
        if device_pixel_ratio is not None:
            self._last_dpr = float(max(device_pixel_ratio, 1e-6))
        if lock or not self._pivot_locked:
            self._pivot_screen_px = (
                float(screen_pos[0]), float(screen_pos[1]))
        if lock:
            self._pivot_locked = True
            self._lock_reference_view = view
            self._lock_reference_phase_offset_px = self._phase_offset_px
            self._lock_viewport_logical_px = self._last_viewport_logical_px
            self._lock_dpr = self._last_dpr
            # Compute the frozen texture coordinate at the pivot so that
            # on_view_changed can correctly restore it during rotation/zoom.
            if view is not None and viewport_logical_px is not None:
                _dpr = float(max(
                    device_pixel_ratio if device_pixel_ratio is not None
                    else self._last_dpr,
                    1e-6,
                ))
                _origin = self._origin_logical(view, viewport_logical_px)
                _off_x = float(self._phase_offset_px[0]) / _dpr
                _off_y = float(self._phase_offset_px[1]) / _dpr
                _vx = float(screen_pos[0]) - _origin[0] - _off_x
                _vy = float(screen_pos[1]) - _origin[1] - _off_y
                # tex_coord = R(-theta) * (vx, vy)
                # R(-theta) = [[cos t, sin t], [-sin t, cos t]]
                _theta = float(view.rotation_radians)
                _c = math.cos(_theta)
                _s = math.sin(_theta)
                self._lock_tex_coord_at_pivot = (
                    _c * _vx + _s * _vy,
                    -_s * _vx + _c * _vy,
                )
            else:
                self._lock_tex_coord_at_pivot = None

    def clear_interaction_pivot_lock(self) -> None:
        self._pivot_locked = False
        self._pin_view_changes = True
        self._lock_reference_view = None
        self._lock_tex_coord_at_pivot = None

    def set_texture(self, texture: QImage | np.ndarray) -> None:
        self._source_rgba8 = self._coerce_to_rgba8(texture)
        self._prepared_rgba8 = self._preprocess_rgba8(self._source_rgba8)
        self._invalidate_texture_cache()

    def set_scale(self, scale: float) -> None:
        self.scale = max(float(scale), 1e-6)
        self._cpu_texture_image_cache.clear()
        self.request_repaint()

    def set_opacity(self, opacity: float) -> None:
        self.opacity = max(0.0, min(1.0, float(opacity)))
        self.request_repaint()

    def set_preprocess_config(
        self,
        *,
        max_texture_dim_px: int | None = None,
        enforce_power_of_two: bool | None = None,
    ) -> None:
        if max_texture_dim_px is not None:
            self.max_texture_dim_px = max(1, int(max_texture_dim_px))
        if enforce_power_of_two is not None:
            self.enforce_power_of_two = bool(enforce_power_of_two)
        self._prepared_rgba8 = self._preprocess_rgba8(self._source_rgba8)
        self._invalidate_texture_cache()

    def paint(self, ctx: CanvasPaintContext) -> None:
        dpr = self._device_pixel_ratio(ctx)
        self._last_dpr = dpr
        self._last_viewport_logical_px = (
            float(ctx.viewport_size_px[0]),
            float(ctx.viewport_size_px[1]),
        )

        ox, oy = self._phase_offset_px
        if not (math.isfinite(ox) and math.isfinite(oy)):
            self._phase_offset_px = (0.0, 0.0)

        if self._use_sampled_cpu_path(ctx):
            self._paint_cpu_sampled(ctx, dpr)
            return

        texture_img = self._tiled_texture_image_for_dpr(dpr)
        p = ctx.painter
        viewport = p.viewport()
        origin_x, origin_y = self._origin_logical(
            ctx.view, ctx.viewport_size_px)
        logical_offset_x = float(self._phase_offset_px[0]) / max(dpr, 1e-6)
        logical_offset_y = float(self._phase_offset_px[1]) / max(dpr, 1e-6)

        p.save()
        try:
            brush = QBrush()
            brush.setTextureImage(texture_img)
            if abs(float(ctx.view.rotation_radians)) > 1e-6:
                brush.setTransform(
                    QTransform().rotateRadians(float(ctx.view.rotation_radians))
                )
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.setOpacity(self.opacity)
            p.setBrushOrigin(origin_x + logical_offset_x,
                             origin_y + logical_offset_y)
            p.fillRect(viewport, brush)
        finally:
            p.restore()

    def _use_sampled_cpu_path(self, ctx: CanvasPaintContext) -> bool:
        # Use sampled CPU rendering only when drawing via a GL-backed widget.
        # On pure QWidget canvases the QBrush texture-pattern path is much
        # faster and stable; sampled path remains as the safe fallback for
        # GL-backed painter composition edge-cases.
        _ = ctx
        return self._has_gpu_context

    def _paint_cpu_sampled(self, ctx: CanvasPaintContext, dpr: float) -> None:
        p = ctx.painter
        vw, vh = (
            float(ctx.viewport_size_px[0]),
            float(ctx.viewport_size_px[1]),
        )
        width_px = max(1, int(round(vw * dpr)))
        height_px = max(1, int(round(vh * dpr)))

        tex = self._prepared_rgba8
        tex_h, tex_w, _ = tex.shape
        tile_w_px = max(1e-6, float(tex_w) / self.scale)
        tile_h_px = max(1e-6, float(tex_h) / self.scale)

        xs = np.arange(width_px, dtype=np.float32)[None, :]
        ys = np.arange(height_px, dtype=np.float32)[:, None]
        frag_y = float(height_px) - ys

        centered_x = (xs / max(dpr, 1e-6)) - (vw * 0.5)
        centered_y = (frag_y / max(dpr, 1e-6)) - (vh * 0.5)

        rot = float(ctx.view.rotation_radians)
        c = math.cos(rot)
        s = math.sin(rot)
        axes_x = c * centered_x + s * centered_y
        axes_y = s * centered_x - c * centered_y

        anchor_x = float(ctx.view.center_world[0]) * float(ctx.view.zoom)
        anchor_y = float(ctx.view.center_world[1]) * float(ctx.view.zoom)
        mapped_x = (axes_x + anchor_x) * dpr + float(self._phase_offset_px[0])
        mapped_y = (axes_y + anchor_y) * dpr + float(self._phase_offset_px[1])

        tx = np.floor(np.mod(mapped_x, tile_w_px) /
                      tile_w_px * tex_w).astype(np.int32)
        ty = np.floor(np.mod(mapped_y, tile_h_px) /
                      tile_h_px * tex_h).astype(np.int32)
        tx = np.clip(tx, 0, tex_w - 1)
        ty = np.clip(ty, 0, tex_h - 1)

        rgba = tex[ty, tx].copy()
        if self.opacity < 1.0:
            rgba[..., 3] = np.clip(
                np.round(rgba[..., 3].astype(np.float32)
                         * float(self.opacity)),
                0,
                255,
            ).astype(np.uint8)

        image = self._array_to_qimage(rgba)
        image.setDevicePixelRatio(dpr)

        p.save()
        try:
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.drawImage(0, 0, image)
        finally:
            p.restore()

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        self._last_viewport_logical_px = (
            float(viewport_logical_px[0]),
            float(viewport_logical_px[1]),
        )
        self._last_dpr = float(max(device_pixel_ratio, 1e-6))
        renderer.render_texture_canvas_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    def on_view_changed(self, transform: ViewTransform) -> None:
        previous = self._last_view
        self._last_view = transform
        if not self._pin_view_changes:
            return
        pivot = self._pivot_screen_px
        if pivot is None:
            vw, vh = self._last_viewport_logical_px
            pivot = (0.5 * vw, 0.5 * vh)

        if self._pivot_locked and self._lock_reference_view is not None:
            tex = self._lock_tex_coord_at_pivot
            if tex is not None:
                # Correct formula: find the brush origin offset that keeps the
                # frozen texture coordinate at the pivot, accounting for both
                # translation and rotation of the brush pattern.
                #   R(-θ_cur) * (pivot - origin_cur - offset_logical) = tex
                #   pivot - origin_cur - offset_logical = R(θ_cur) * tex
                #   offset_logical = pivot - origin_cur - R(θ_cur) * tex
                _origin_cur = self._origin_logical(
                    transform, self._lock_viewport_logical_px)
                _dpr = max(float(self._lock_dpr), 1e-6)
                _theta = float(transform.rotation_radians)
                _c = math.cos(_theta)
                _s = math.sin(_theta)
                # R(θ) * tex
                _rot_tx = _c * tex[0] - _s * tex[1]
                _rot_ty = _s * tex[0] + _c * tex[1]
                _new_off_lx = float(pivot[0]) - _origin_cur[0] - _rot_tx
                _new_off_ly = float(pivot[1]) - _origin_cur[1] - _rot_ty
                self._phase_offset_px = (
                    _new_off_lx * _dpr,
                    _new_off_ly * _dpr,
                )
            else:
                # Fallback: translation-based formula (no rotation change)
                ref_mapped = self._mapped_physical_px(
                    self._lock_reference_view,
                    pivot,
                    self._lock_viewport_logical_px,
                    self._lock_dpr,
                )
                cur_mapped = self._mapped_physical_px(
                    transform,
                    pivot,
                    self._lock_viewport_logical_px,
                    self._lock_dpr,
                )
                self._phase_offset_px = (
                    self._lock_reference_phase_offset_px[0]
                    + (ref_mapped[0] - cur_mapped[0]),
                    self._lock_reference_phase_offset_px[1]
                    + (ref_mapped[1] - cur_mapped[1]),
                )
            self._phase_offset_px = self._wrapped_phase_offset(
                self._phase_offset_px)
            return

        if previous is None:
            return

        prev_mapped = self._mapped_physical_px(
            previous,
            pivot,
            self._last_viewport_logical_px,
            self._last_dpr,
        )
        next_mapped = self._mapped_physical_px(
            transform,
            pivot,
            self._last_viewport_logical_px,
            self._last_dpr,
        )
        ox, oy = self._phase_offset_px
        self._phase_offset_px = (
            ox + (prev_mapped[0] - next_mapped[0]),
            oy + (prev_mapped[1] - next_mapped[1]),
        )
        self._phase_offset_px = self._wrapped_phase_offset(
            self._phase_offset_px)

    @staticmethod
    def _default_noise_texture(size: int = 256) -> np.ndarray:
        size = max(64, int(size))
        yy, xx = np.mgrid[0:size, 0:size]
        rgba = np.empty((size, size, 4), dtype=np.uint8)

        # Keep the edges quiet so repeated tiling stays visually stable during
        # pan/zoom/rotate diagnostics. All strong features live inside a safe
        # margin and the outer border remains near-uniform.
        rgba[..., 0] = np.clip(224 + ((xx * 13 + yy * 5) % 9) - 4, 0, 255)
        rgba[..., 1] = np.clip(224 + ((xx * 7 + yy * 11) % 11) - 5, 0, 255)
        rgba[..., 2] = np.clip(222 + ((xx * 3 + yy * 17) % 7) - 3, 0, 255)
        rgba[..., 3] = 255

        minor = max(8, size // 16)
        major = minor * 4
        rgba[((xx % minor) == 0) | ((yy % minor) == 0), :3] = (194, 196, 200)
        rgba[((xx % major) == 0) | ((yy % major) == 0), :3] = (112, 116, 124)

        margin = max(20, size // 7)
        inner = (
            (xx >= margin)
            & (xx < size - margin)
            & (yy >= margin)
            & (yy < size - margin)
        )

        # Bold red horizontal arrow fully inside the tile.
        shaft_h = max(12, size // 18)
        shaft_y0 = size // 3
        shaft_x0 = margin + max(4, size // 18)
        shaft_x1 = size - margin - max(18, size // 8)
        shaft_mask = (
            (yy >= shaft_y0)
            & (yy < shaft_y0 + shaft_h)
            & (xx >= shaft_x0)
            & (xx < shaft_x1)
        )
        rgba[shaft_mask, :3] = (206, 44, 44)
        head_half = max(18, size // 10)
        head_len = max(20, size // 9)
        head_cy = shaft_y0 + shaft_h // 2
        head_mask = (
            (xx >= shaft_x1)
            & (xx < shaft_x1 + head_len)
            & (np.abs(yy - head_cy) <= ((shaft_x1 + head_len - xx) * head_half / max(head_len, 1)))
        )
        rgba[head_mask & inner, :3] = (206, 44, 44)

        # Bold blue diagonal band, also fully inside the tile.
        diag_center = size * 0.62
        diag_width = max(12, size // 18)
        diag_mask = inner & (
            np.abs((xx * 0.9 + yy * 0.55) - diag_center) <= diag_width)
        rgba[diag_mask, :3] = (52, 82, 204)

        # Yellow target ring off-center for zoom/pivot diagnostics.
        target_cx = int(size * 0.68)
        target_cy = int(size * 0.68)
        target_r = max(16, size // 10)
        ring_w = max(5, size // 36)
        dist2 = (xx - target_cx) ** 2 + (yy - target_cy) ** 2
        ring = inner & (dist2 <= target_r ** 2) & (dist2 >=
                                                   (target_r - ring_w) ** 2)
        dot = inner & (dist2 <= max(6, size // 44) ** 2)
        rgba[ring, :3] = (224, 184, 46)
        rgba[dot, :3] = (30, 30, 30)

        # Small green locator block to break symmetry without touching seams.
        block = inner & (xx >= margin + max(8, size // 20)) & (xx < margin + max(34, size // 7)) & (
            yy >= size - margin - max(34, size // 7)) & (yy < size - margin - max(8, size // 20))
        rgba[block, :3] = (44, 156, 82)
        return rgba

    @staticmethod
    def _coerce_to_rgba8(texture: QImage | np.ndarray) -> np.ndarray:
        if isinstance(texture, QImage):
            qimg = texture.convertToFormat(QImage.Format.Format_RGBA8888)
            width = qimg.width()
            height = qimg.height()
            buffer = qimg.constBits()
            return np.frombuffer(
                buffer,
                dtype=np.uint8,
                count=width * height * 4,
            ).reshape(height, width, 4).copy()

        arr = np.asarray(texture)
        if arr.ndim == 2:
            arr_u8 = np.clip(arr, 0, 255).astype(np.uint8)
            rgba = np.empty((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
            rgba[..., 0] = arr_u8
            rgba[..., 1] = arr_u8
            rgba[..., 2] = arr_u8
            rgba[..., 3] = 255
            return rgba
        if arr.ndim == 3 and arr.shape[2] in (3, 4):
            arr_u8 = np.clip(arr, 0, 255).astype(np.uint8)
            if arr.shape[2] == 4:
                return arr_u8.copy()
            rgba = np.empty((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
            rgba[..., 0:3] = arr_u8
            rgba[..., 3] = 255
            return rgba
        raise ValueError(
            "Texture must be QImage or ndarray with shape HxW, HxWx3, or HxWx4")

    def _preprocess_rgba8(self, rgba8: np.ndarray) -> np.ndarray:
        h, w, _ = rgba8.shape
        max_dim = self.max_texture_dim_px

        scale = min(1.0, float(max_dim) / float(max(h, w)))
        resized_w = max(1, int(round(w * scale)))
        resized_h = max(1, int(round(h * scale)))

        target_w = resized_w
        target_h = resized_h
        if self.enforce_power_of_two:
            target_w = self._nearest_power_of_two(resized_w)
            target_h = self._nearest_power_of_two(resized_h)
            target_w = min(max_dim, max(1, target_w))
            target_h = min(max_dim, max(1, target_h))

        if target_w == w and target_h == h:
            return rgba8.copy()

        qimg = self._array_to_qimage(rgba8)
        resized = qimg.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return self._coerce_to_rgba8(resized)

    @staticmethod
    def _nearest_power_of_two(value: int) -> int:
        if value <= 1:
            return 1
        exponent = int(round(math.log(value, 2.0)))
        return max(1, 2**exponent)

    @staticmethod
    def _array_to_qimage(rgba8: np.ndarray) -> QImage:
        h, w, _ = rgba8.shape
        qimg = QImage(
            rgba8.data,
            w,
            h,
            w * 4,
            QImage.Format.Format_RGBA8888,
        ).copy()
        return qimg.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    def _invalidate_texture_cache(self) -> None:
        self._cpu_texture_image_cache.clear()
        self._texture_revision += 1
        self.request_repaint()

    def _tiled_texture_image_for_dpr(self, dpr: float) -> QImage:
        dpr_milli = max(1, int(round(dpr * 1000.0)))
        scale_milli = max(1, int(round(self.scale * 1000.0)))
        key = (dpr_milli, scale_milli)
        cached = self._cpu_texture_image_cache.get(key)
        if cached is not None:
            return cached

        h, w, _ = self._prepared_rgba8.shape
        scaled_w = max(1, int(round(float(w) / (self.scale * dpr))))
        scaled_h = max(1, int(round(float(h) / (self.scale * dpr))))

        qimg = self._array_to_qimage(self._prepared_rgba8)
        if scaled_w != w or scaled_h != h:
            qimg = qimg.scaled(
                scaled_w,
                scaled_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self._cpu_texture_image_cache[key] = qimg
        return qimg

    def _wrapped_phase_offset(
        self,
        offset_px: tuple[float, float],
    ) -> tuple[float, float]:
        # Keep an unwrapped running phase to avoid visible discontinuities
        # when camera animation crosses tile boundaries.
        return (float(offset_px[0]), float(offset_px[1]))

    def _tile_size_px(self) -> tuple[float, float]:
        h, w, _ = self._prepared_rgba8.shape
        tile_w = max(1.0, float(w) / self.scale)
        tile_h = max(1.0, float(h) / self.scale)
        return (tile_w, tile_h)

    @staticmethod
    def _mapped_physical_px(
        view: ViewTransform,
        screen_logical: tuple[float, float],
        viewport_logical_px: tuple[float, float],
        dpr: float,
    ) -> tuple[float, float]:
        sx, sy = float(screen_logical[0]), float(screen_logical[1])
        vw, vh = float(viewport_logical_px[0]), float(viewport_logical_px[1])
        centered_x = sx - (vw * 0.5)
        centered_y = sy - (vh * 0.5)

        c = math.cos(float(view.rotation_radians))
        s = math.sin(float(view.rotation_radians))
        world_axes_x = c * centered_x + s * centered_y
        world_axes_y = s * centered_x - c * centered_y

        anchor_x = float(view.center_world[0]) * float(view.zoom)
        anchor_y = float(view.center_world[1]) * float(view.zoom)
        dpr_safe = max(float(dpr), 1e-6)
        return (
            (world_axes_x + anchor_x) * dpr_safe,
            (world_axes_y + anchor_y) * dpr_safe,
        )

    @staticmethod
    def _origin_logical(
        view: ViewTransform,
        viewport_size_px: tuple[float, float],
    ) -> tuple[float, float]:
        half_w = viewport_size_px[0] * 0.5
        half_h = viewport_size_px[1] * 0.5
        x = half_w - float(view.center_world[0]) * float(view.zoom)
        y = half_h + float(view.center_world[1]) * float(view.zoom)
        return (x, y)

    @staticmethod
    def _device_pixel_ratio(ctx: CanvasPaintContext) -> float:
        dpr = max(ctx.device_pixel_ratio, 1.0)
        device = ctx.painter.device()
        getter = getattr(device, "devicePixelRatioF", None)
        if callable(getter):
            dpr = max(dpr, float(getter()))
        return dpr


__all__ = ["TextureCanvasOverlay"]
