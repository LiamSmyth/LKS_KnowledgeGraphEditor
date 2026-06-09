"""`CanvasBorderOverlay`: AA outline around a configurable world AABB."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPen

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_gpu_overlay_renderer import (
        Canvas2DGPUOverlayRenderer,
    )
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform


class CanvasBorderOverlay(ViewportOverlay):
    """Anti-aliased outline of a world-space AABB.

    Args:
        world_aabb: World-space rectangle to outline.
        line_width_px: Stroke width in **screen pixels** (the line stays
            constant width regardless of zoom).
    """

    screen_space = False  # paints in world-space; pen is cosmetic
    supports_gpu_rendering = True

    def __init__(self, world_aabb: AABB, line_width_px: float = 1.0) -> None:
        super().__init__()
        self.world_aabb = world_aabb
        self.line_width_px = float(line_width_px)
        self._color = QColor(PALETTE["canvas_border"])

    def bounds(self) -> AABB | None:
        return self.world_aabb

    @property
    def color(self) -> QColor:
        return QColor(self._color)

    def paint(self, ctx: CanvasPaintContext) -> None:
        p = ctx.painter
        pen = QPen(self._color)
        pen.setCosmetic(True)  # constant pixel width regardless of transform
        pen.setWidthF(self.line_width_px)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        a = self.world_aabb
        p.drawRect(QRectF(a.x0, a.y0, a.width, a.height))

    def render_gpu(
        self,
        renderer: Canvas2DGPUOverlayRenderer,
        view: ViewTransform,
        viewport_px: tuple[int, int],
        viewport_logical_px: tuple[float, float],
        device_pixel_ratio: float,
    ) -> None:
        renderer.render_canvas_border_overlay(
            self,
            view,
            viewport_px,
            viewport_logical_px,
            device_pixel_ratio,
        )

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        a = self.world_aabb
        return {
            "type": "canvas2d.overlays.canvas_border",
            "x0": a.x0,
            "y0": a.y0,
            "x1": a.x1,
            "y1": a.y1,
            "line_width_px": self.line_width_px,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CanvasBorderOverlay:
        aabb = AABB(
            float(d.get("x0", -100.0)),
            float(d.get("y0", -100.0)),
            float(d.get("x1", 100.0)),
            float(d.get("y1", 100.0)),
        )
        return cls(
            world_aabb=aabb,
            line_width_px=float(d.get("line_width_px", 1.0)),
        )


__all__ = ["CanvasBorderOverlay"]
