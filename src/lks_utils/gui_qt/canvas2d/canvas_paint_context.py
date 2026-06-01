"""`CanvasPaintContext`: per-frame paint context handed to items.

Items use the context's `painter` (Qt's `QPainter`) to draw. The
context exposes the active `ViewTransform`, viewport size, dirty
region, and a pre-computed world->screen transform applied to the
painter so items draw in *world coordinates*.

Geometry can be painted directly in world space. Text is a special
case because the world transform includes a Y flip; use
`draw_text_at_world` to anchor upright glyphs at a world-space
position without manually resetting the painter transform.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.view_transform import ViewTransform
from lks_utils.spatial.aabb import AABB

if TYPE_CHECKING:
    from PySide6.QtGui import QPainter


@dataclass
class CanvasPaintContext:
    """Per-frame state delivered to `CanvasItem.paint`.

    Attributes:
        painter: Active `QPainter`. By default its world transform is
            already set so coordinates are world-space; items that need
            screen-space rendering should call ``painter.save()``,
            ``painter.resetTransform()``, do their thing, then
            ``painter.restore()``.
        view: The `ViewTransform` for the current frame.
        viewport_size_px: ``(width, height)`` of the widget in logical
            pixels.
        viewport_aabb_world: World-space AABB covering the visible
            viewport (already accounts for rotation).
        dirty_region_world: World-space AABB describing what changed
            since the last frame, or ``None`` for "full repaint".
            Items may skip work that doesn't intersect.
        device_pixel_ratio: HiDPI scale factor (Qt `devicePixelRatioF`).
    """

    painter: "QPainter"
    view: ViewTransform
    viewport_size_px: tuple[float, float]
    viewport_aabb_world: AABB
    dirty_region_world: AABB | None = None
    device_pixel_ratio: float = 1.0

    def world_to_screen(self, world_pos: tuple[float, float]) -> tuple[float, float]:
        """Project a world-space point into screen space."""
        return self.view.world_to_screen(world_pos, self.viewport_size_px)

    def draw_text_at_world(
        self,
        text: str,
        world_pos: tuple[float, float],
        *,
        font,
        color,
        centered: bool = False,
        pixel_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """Draw upright text anchored by a world-space position.

        The anchor is supplied in world coordinates, but glyphs are
        rasterized in screen space so the canvas Y-flip does not mirror
        the text.
        """
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QPainterPath

        sx, sy = self.world_to_screen(world_pos)
        sx += pixel_offset[0]
        sy += pixel_offset[1]

        painter = self.painter
        painter.save()
        painter.resetTransform()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(text)
        text_h = metrics.height()
        text_x = float(sx - text_w / 2.0) if centered else float(sx)
        text_y = float(sy + text_h / 4.0)
        text_path = QPainterPath()
        text_path.addText(QPointF(text_x, text_y), font, text)
        painter.drawPath(text_path)
        painter.restore()


__all__ = ["CanvasPaintContext"]
