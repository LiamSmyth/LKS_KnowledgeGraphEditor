"""Decorative edge item used by the knowledge decomposition canvas."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF

from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.knowledge.default_theme import EDGE_COLOR
from lks_utils.spatial.aabb import AABB


class _KnowledgeEdgeCanvasItem(CanvasItem):
    """Bezier edge in world space connecting two anchor points."""

    selectable = False
    draggable = False

    def __init__(
        self,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        *,
        color: str | None = None,
        label: str | None = None,
        dashed: bool = False,
        arrow_at_end: bool = False,
        arrow_at_start: bool = False,
    ) -> None:
        self._x0 = x0
        self._y0 = y0
        self._x1 = x1
        self._y1 = y1
        self._color = color
        self._label = label
        self._dashed = dashed
        self._arrow_at_end = arrow_at_end
        self._arrow_at_start = arrow_at_start

    def bounds(self) -> AABB:
        # Decorative-only edge, excluded from selection hit queries.
        return None

    def paint(self, ctx: CanvasPaintContext) -> None:
        stroke = QColor(self._color) if self._color else QColor(EDGE_COLOR)
        pen = QPen(stroke, 1.5)
        pen.setCosmetic(True)
        pen.setStyle(
            Qt.PenStyle.DashLine if self._dashed else Qt.PenStyle.SolidLine)
        ctx.painter.setPen(pen)
        ctx.painter.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(self._x0, self._y0)
        mid_y = (self._y0 + self._y1) / 2.0
        path.cubicTo(self._x0, mid_y, self._x1, mid_y, self._x1, self._y1)
        ctx.painter.drawPath(path)

        if self._arrow_at_end or self._arrow_at_start:
            dx = self._x1 - self._x0
            dy = self._y1 - self._y0
            length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
            ux = dx / length
            uy = dy / length
            arrow_len = 9.0
            arrow_w = 4.5

            if self._arrow_at_end:
                arrow_x = self._x1
                arrow_y = self._y1
            else:
                arrow_x = self._x0
                arrow_y = self._y0
                ux = -ux
                uy = -uy

            bx = arrow_x - ux * arrow_len
            by = arrow_y - uy * arrow_len
            px = -uy
            py = ux

            ctx.painter.setBrush(QColor(self._color)
                                 if self._color else QColor(EDGE_COLOR))
            arrow_pts = [
                QPointF(arrow_x, arrow_y),
                QPointF(bx + px * arrow_w, by + py * arrow_w),
                QPointF(bx - px * arrow_w, by - py * arrow_w),
            ]
            ctx.painter.drawPolygon(QPolygonF(arrow_pts))

        if self._label:
            painter = ctx.painter
            painter.save()
            painter.setPen(QPen(stroke, 1.0))
            font = painter.font()
            font.setPointSizeF(max(7.0, font.pointSizeF() - 1.0))
            painter.setFont(font)
            label_x = (self._x0 + self._x1) * 0.5 + 6.0
            label_y = (self._y0 + self._y1) * 0.5 + 5.0
            painter.translate(label_x, label_y)
            painter.scale(1.0, -1.0)
            painter.drawText(0.0, 0.0, self._label)
            painter.restore()


__all__ = ["_KnowledgeEdgeCanvasItem"]
