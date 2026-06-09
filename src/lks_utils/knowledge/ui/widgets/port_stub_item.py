"""Canvas2D item that renders a directional ad-hoc link stub."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtSvg import QSvgRenderer

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext
from lks_utils.knowledge.default_theme import (
    ADHOC_STUB_INCOMING_COLOR,
    ADHOC_STUB_OUTGOING_COLOR,
    ADHOC_STUB_TEXT_COLOR,
)
from lks_utils.spatial.aabb import AABB


class QKnowledgePortStubCanvasObject(CanvasObject):
    """Non-interactive directional stub for one ad-hoc link."""

    selectable: bool = False
    draggable: bool = False

    _LINE_LENGTH_WORLD: float = 42.0
    _ARROW_SIZE_WORLD: float = 5.0
    _LANE_HEIGHT_WORLD: float = 18.0
    _TEXT_OFFSET_WORLD: float = 6.0
    _PORTAL_W_WORLD: float = 8.0
    _PORTAL_H_WORLD: float = 16.0
    _NODE_GAP_WORLD: float = 2.0
    _ANGLE_FACTOR: float = 0.28
    _ANGLE_MAX_WORLD: float = 10.0

    def __init__(
        self,
        *,
        node_id: str,
        node_bounds: AABB,
        direction: str,
        index: int,
        count: int,
        link_type_id: str | None = None,
        link_type_name: str | None = None,
        inverse_link_type_name: str | None = None,
        peer_node_id: str | None = None,
        peer_node_name: str | None = None,
        display_color: str | None = None,
    ) -> None:
        if direction not in {"incoming", "outgoing"}:
            raise ValueError("direction must be 'incoming' or 'outgoing'")
        if count < 1:
            raise ValueError("count must be at least 1")

        self.node_id = node_id
        self._node_bounds = node_bounds
        self._direction = direction
        self._index = index
        self._count = count
        self._link_type_id = link_type_id
        self._link_type_name = link_type_name
        self._inverse_link_type_name = inverse_link_type_name
        self._peer_node_id = peer_node_id
        self._peer_node_name = peer_node_name
        self._display_color = display_color
        icon_dir = Path(__file__).resolve().parents[1] / "data" / "icons"
        self._incoming_svg = QSvgRenderer(str(icon_dir / "incoming_glyph.svg"))
        self._outgoing_svg = QSvgRenderer(str(icon_dir / "outgoing_glyph.svg"))

    @property
    def direction(self) -> str:
        return self._direction

    def bounds(self) -> AABB:
        lane_y = self._lane_center_y()
        remote_y = self._remote_anchor_y(lane_y)
        y_min = min(lane_y, remote_y)
        y_max = max(lane_y, remote_y)
        if self._direction == "outgoing":
            x0 = self._node_bounds.x1 + self._NODE_GAP_WORLD
            x1 = x0 + self._LINE_LENGTH_WORLD + self._PORTAL_W_WORLD * 0.5
        else:
            x1 = self._node_bounds.x0 - self._NODE_GAP_WORLD
            x0 = x1 - self._LINE_LENGTH_WORLD - self._PORTAL_W_WORLD * 0.5
        half_h = self._LANE_HEIGHT_WORLD * 0.5
        return AABB(x0, y_min - half_h, x1, y_max + half_h)

    def paint(self, ctx: CanvasPaintContext) -> None:
        painter = ctx.painter
        stroke_color = QColor(self._display_color) if self._display_color else QColor(
            ADHOC_STUB_OUTGOING_COLOR if self._direction == "outgoing" else ADHOC_STUB_INCOMING_COLOR
        )
        pen = QPen(stroke_color, 1.6)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        font = QFont(painter.font())
        font.setPointSizeF(max(6.0, font.pointSizeF() - 2.0))
        font.setItalic(True)
        painter.setFont(font)

        lane_y = self._lane_center_y()
        remote_y = self._remote_anchor_y(lane_y)
        label_text = self._display_label()
        text_width = max(60.0, float(
            painter.fontMetrics().horizontalAdvance(label_text)))
        if self._direction == "outgoing":
            line_start = self._node_bounds.x1 + self._NODE_GAP_WORLD
            line_end = line_start + self._LINE_LENGTH_WORLD
            self._draw_portal_glyph(
                painter=painter,
                center_x=line_end,
                lane_y=remote_y,
                side="right",
                color=stroke_color,
            )
            painter.drawLine(line_start, lane_y, line_end, remote_y)
            self._draw_arrow_head(
                painter=painter,
                tail_x=line_start,
                tail_y=lane_y,
                tip_x=line_end,
                tip_y=remote_y,
                color=stroke_color,
            )
            painter.setPen(QPen(stroke_color if self._display_color else QColor(
                ADHOC_STUB_TEXT_COLOR), 1.0))
            painter.save()
            painter.translate(line_end + self._TEXT_OFFSET_WORLD, remote_y)
            painter.scale(1.0, -1.0)
            painter.drawText(0.0, 0.0, label_text)
            painter.restore()
        else:
            line_end = self._node_bounds.x0 - self._NODE_GAP_WORLD
            line_start = line_end - self._LINE_LENGTH_WORLD
            self._draw_portal_glyph(
                painter=painter,
                center_x=line_start,
                lane_y=remote_y,
                side="left",
                color=stroke_color,
            )
            painter.drawLine(line_start, remote_y, line_end, lane_y)
            self._draw_arrow_head(
                painter=painter,
                tail_x=line_start,
                tail_y=remote_y,
                tip_x=line_end,
                tip_y=lane_y,
                color=stroke_color,
            )
            painter.setPen(QPen(stroke_color if self._display_color else QColor(
                ADHOC_STUB_TEXT_COLOR), 1.0))
            painter.save()
            text_x = line_start - self._TEXT_OFFSET_WORLD - text_width
            painter.translate(text_x, remote_y)
            painter.scale(1.0, -1.0)
            painter.drawText(0.0, 0.0, label_text)
            painter.restore()

    def tooltip_at(self, world_pt: tuple[float, float]) -> str | None:
        if not self.hit_test(world_pt):
            return None
        direction = "Outgoing" if self._direction == "outgoing" else "Incoming"
        lines = [f"{direction} ad-hoc link",
                 f"Remote node: {self._peer_display_name()}"]
        if self._link_type_name:
            lines.append(f"Type: {self._link_type_name}")
        elif self._link_type_id:
            lines.append(f"Type: {self._link_type_id}")
        return "\n".join(lines)

    def _display_label(self) -> str:
        if self._direction == "incoming" and self._inverse_link_type_name:
            type_part = self._inverse_link_type_name
        else:
            type_part = self._link_type_name or self._link_type_id or "(unknown type)"
        return f"{type_part}: {self._peer_display_name()}"

    def _peer_display_name(self) -> str:
        if self._peer_node_name:
            return self._peer_node_name
        if self._peer_node_id:
            return f"(missing:{self._peer_node_id[-8:]})"
        return "(unknown target)"

    def _draw_portal_glyph(
        self,
        *,
        painter: QPainter,
        center_x: float,
        lane_y: float,
        side: str,
        color: QColor,
    ) -> None:
        """Draw the actual SVG portal glyph centered on the stub endpoint.

        Render at 4x then downsample to reduce blur while preserving tint.
        """
        renderer = self._outgoing_svg if side == "right" else self._incoming_svg
        w = max(1, int(round(self._PORTAL_W_WORLD)))
        h = max(1, int(round(self._PORTAL_H_WORLD)))
        scale = 4
        hi_w = w * scale
        hi_h = h * scale

        image = QImage(hi_w, hi_h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        image_painter = QPainter(image)
        image_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(image_painter, QRect(0, 0, hi_w, hi_h))
        image_painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn)
        image_painter.fillRect(0, 0, hi_w, hi_h, color)
        image_painter.end()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = QRect(
            int(round(center_x - self._PORTAL_W_WORLD * 0.5)),
            int(round(lane_y - self._PORTAL_H_WORLD * 0.5)),
            w,
            h,
        )
        painter.drawImage(rect, image)
        painter.restore()

    def _remote_anchor_y(self, lane_y: float) -> float:
        center_y = (self._node_bounds.y0 + self._node_bounds.y1) * 0.5
        delta = lane_y - center_y
        if abs(delta) < 1e-6:
            return lane_y
        offset = min(self._ANGLE_MAX_WORLD, abs(delta) * self._ANGLE_FACTOR)
        return lane_y + (offset if delta > 0.0 else -offset)

    def _draw_arrow_head(
        self,
        *,
        painter: QPainter,
        tail_x: float,
        tail_y: float,
        tip_x: float,
        tip_y: float,
        color: QColor,
    ) -> None:
        dx = tip_x - tail_x
        dy = tip_y - tail_y
        length = max(1e-6, (dx * dx + dy * dy) ** 0.5)
        ux = dx / length
        uy = dy / length
        px = -uy
        py = ux
        base_x = tip_x - ux * (self._ARROW_SIZE_WORLD + 1.5)
        base_y = tip_y - uy * (self._ARROW_SIZE_WORLD + 1.5)
        wing = self._ARROW_SIZE_WORLD * 0.8

        path = QPainterPath()
        path.moveTo(tip_x, tip_y)
        path.lineTo(base_x + px * wing, base_y + py * wing)
        path.lineTo(base_x - px * wing, base_y - py * wing)
        path.closeSubpath()

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
        painter.restore()

    def _lane_center_y(self) -> float:
        top = self._node_bounds.y1 - 28.0
        bottom = self._node_bounds.y0 + 12.0
        if self._count == 1:
            return (top + bottom) * 0.5
        step = max(1.0, (top - bottom) / float(self._count))
        return top - (step * (self._index + 0.5))


__all__ = ["QKnowledgePortStubCanvasObject"]
