"""`CoordHudOverlay`: text overlay showing cursor world coords + zoom %."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath

from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_overlay import ViewportOverlay
from lks_utils.gui_qt.theme.palette import PALETTE


class CoordHudOverlay(ViewportOverlay):
    """Bottom-left HUD showing cursor world coords and zoom %.

    Subscribes to the host `Canvas2D.cursor_world_pos` signal via
    :meth:`attach`.
    """

    screen_space = True

    def __init__(self) -> None:
        super().__init__()
        self._cursor_world: tuple[float, float] | None = None
        self._canvas = None  # set in attach
        self._font = QFont("Consolas", 9)
        self._color = QColor(PALETTE["canvas2d_hud_text"])
        self._bg = QColor(0, 0, 0, 160)

    def attach(self, canvas) -> None:  # noqa: ANN001
        """Connect to a `Canvas2D`'s cursor signal."""
        self._canvas = canvas
        canvas.cursor_world_pos.connect(self._on_cursor)

    def _on_cursor(self, x: float, y: float) -> None:
        self._cursor_world = (x, y)
        self.request_repaint()

    def paint(self, ctx: CanvasPaintContext) -> None:
        p = ctx.painter
        vw, vh = ctx.viewport_size_px
        lines: list[str] = []
        if self._cursor_world is not None:
            cx, cy = self._cursor_world
            lines.append(f"world: ({cx:.1f}, {cy:.1f})")
        else:
            lines.append("world: (—)")
        lines.append(f"zoom:  {ctx.view.zoom * 100:.1f}%")
        if ctx.view.rotation_radians != 0.0:
            import math
            deg = math.degrees(ctx.view.rotation_radians) % 360
            lines.append(f"rot:   {deg:.1f}°")
        if self._canvas is not None:
            for s in self._canvas.hud_strings():
                lines.append(s)

        p.setFont(self._font)
        fm = p.fontMetrics()
        line_h = fm.height()
        pad = 6
        text_w = max(fm.horizontalAdvance(s) for s in lines)
        box_w = text_w + 2 * pad
        box_h = line_h * len(lines) + 2 * pad
        x0 = 8
        y0 = vh - box_h - 8
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._bg)
        p.drawRoundedRect(QRectF(x0, y0, box_w, box_h), 3, 3)
        p.setBrush(self._color)
        for i, s in enumerate(lines):
            text_path = QPainterPath()
            text_path.addText(
                float(x0 + pad),
                float(y0 + pad + (i + 1) * line_h - 2),
                self._font,
                s,
            )
            p.drawPath(text_path)

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict:
        return {"type": "canvas2d.overlays.coord_hud"}

    @classmethod
    def from_dict(cls, d: dict) -> CoordHudOverlay:  # noqa: ARG003
        return cls()


__all__ = ["CoordHudOverlay"]
