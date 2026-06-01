"""Canvas2D arrow link primitive for the knowledge graph view."""
from __future__ import annotations

from collections.abc import Callable
from math import sqrt

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen, QPolygonF

from lks_utils.gui_qt.canvas2d.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.canvas_input_event import CanvasInputEvent
from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.knowledge.default_theme import EDGE_COLOR, NODE_SELECTED_STROKE_COLOR, NODE_ACTIVE_SELECTED_STROKE_COLOR, LINK_GHOST_ALPHA
from lks_utils.knowledge.link_type_view_state import LinkTypeFlags
from lks_utils.spatial.aabb import AABB


class QKnowledgeGraphLinkCanvasItem(CanvasItem):
    """Directed graph link with optional selected-state labels."""

    draggable: bool = False
    manages_own_selection_highlight: bool = True

    def __init__(
        self,
        *,
        link_id: str,
        link_type_id: str | None = None,
        source_anchor: tuple[float, float],
        target_anchor: tuple[float, float],
        color: str | None,
        outgoing_label: str | None,
        incoming_label: str | None,
        preview: bool = False,
        view_flags: LinkTypeFlags | None = None,
        on_select: Callable[[QKnowledgeGraphLinkCanvasItem],
                            None] | None = None,
    ) -> None:
        self.link_id = link_id
        self.link_type_id = link_type_id
        self._source_anchor = source_anchor
        self._target_anchor = target_anchor
        self._color = color or EDGE_COLOR
        self._outgoing_label = outgoing_label or ""
        self._incoming_label = incoming_label or ""
        self._preview = bool(preview)
        self._on_select = on_select
        self._selected = False
        self._active_selected = False
        self._view_flags = view_flags or LinkTypeFlags()
        self.selectable = bool(
            self._view_flags.visible and self._view_flags.selectable)

    @property
    def selected(self) -> bool:
        """Return selected state."""
        return self._selected

    @selected.setter
    def selected(self, value: bool) -> None:
        if self._selected == value:
            return
        self._selected = value
        self.request_repaint(self.bounds())

    @property
    def active_selected(self) -> bool:
        """Return whether this selected link is the active selection."""
        return self._active_selected

    @active_selected.setter
    def active_selected(self, value: bool) -> None:
        if self._active_selected == value:
            return
        self._active_selected = value
        self.request_repaint(self.bounds())

    def update_view_flags(self, flags: LinkTypeFlags) -> None:
        """Update the view state flags for this link.

        Args:
            flags: New LinkTypeFlags with visibility, ghosting, selectability settings.
        """
        if self._view_flags == flags:
            return
        self._view_flags = flags
        # Canvas2D selection/rubber-band checks item.selectable directly.
        self.selectable = bool(flags.visible and flags.selectable)
        self.request_repaint(self.bounds())

    def bounds(self) -> AABB:
        x0, y0 = self._source_anchor
        x1, y1 = self._target_anchor
        # Include selected-label extents in the repaint/clip bounds so labels
        # remain visible after adaptive offset positioning.
        pad = 96.0
        return AABB(min(x0, x1) - pad, min(y0, y1) - pad, max(x0, x1) + pad, max(y0, y1) + pad)

    def selection_intersects_aabb(self, world_aabb: AABB) -> bool:
        """Return True when the link segment overlaps the selection AABB."""
        if not self._view_flags.visible or not self._view_flags.selectable:
            return False
        sx, sy = self._source_anchor
        tx, ty = self._target_anchor
        if world_aabb.contains_point(sx, sy) or world_aabb.contains_point(tx, ty):
            return True

        rx0, ry0, rx1, ry1 = world_aabb.x0, world_aabb.y0, world_aabb.x1, world_aabb.y1
        edges = (
            ((rx0, ry0), (rx1, ry0)),
            ((rx1, ry0), (rx1, ry1)),
            ((rx1, ry1), (rx0, ry1)),
            ((rx0, ry1), (rx0, ry0)),
        )
        for edge_start, edge_end in edges:
            if self._segments_intersect((sx, sy), (tx, ty), edge_start, edge_end):
                return True
        return False

    @staticmethod
    def _segments_intersect(
        a0: tuple[float, float],
        a1: tuple[float, float],
        b0: tuple[float, float],
        b1: tuple[float, float],
    ) -> bool:
        """Return True if segments a0-a1 and b0-b1 intersect (inclusive)."""

        def orient(
            p: tuple[float, float],
            q: tuple[float, float],
            r: tuple[float, float],
        ) -> float:
            return ((q[0] - p[0]) * (r[1] - p[1])) - ((q[1] - p[1]) * (r[0] - p[0]))

        def on_segment(
            p: tuple[float, float],
            q: tuple[float, float],
            r: tuple[float, float],
        ) -> bool:
            return (
                min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
                and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
            )

        o1 = orient(a0, a1, b0)
        o2 = orient(a0, a1, b1)
        o3 = orient(b0, b1, a0)
        o4 = orient(b0, b1, a1)

        if ((o1 > 0 and o2 < 0) or (o1 < 0 and o2 > 0)) and ((o3 > 0 and o4 < 0) or (o3 < 0 and o4 > 0)):
            return True

        eps = 1e-9
        if abs(o1) <= eps and on_segment(a0, b0, a1):
            return True
        if abs(o2) <= eps and on_segment(a0, b1, a1):
            return True
        if abs(o3) <= eps and on_segment(b0, a0, b1):
            return True
        if abs(o4) <= eps and on_segment(b0, a1, b1):
            return True

        return False

    def hit_test(self, world_pt: tuple[float, float]) -> bool:
        # Skip hit test if not visible or not selectable
        if not self._view_flags.visible or not self._view_flags.selectable:
            return False

        sx, sy = self._source_anchor
        tx, ty = self._target_anchor
        px, py = world_pt

        vx = tx - sx
        vy = ty - sy
        denom = (vx * vx) + (vy * vy)
        if denom <= 1e-6:
            return False
        t = ((px - sx) * vx + (py - sy) * vy) / denom
        t = max(0.0, min(1.0, t))
        nx = sx + (vx * t)
        ny = sy + (vy * t)
        dx = px - nx
        dy = py - ny
        return (dx * dx + dy * dy) <= (8.0 * 8.0)

    def handle_input(self, event: CanvasInputEvent) -> bool:
        if self._preview:
            return False
        if event.action.id != CANVAS_PRIMARY.id or event.phase != "press":
            return False
        if not self.hit_test(event.world_pos):
            return False
        if self._on_select is not None:
            self._on_select(self)
        return True

    def paint(self, ctx: CanvasPaintContext) -> None:
        # Skip rendering if not visible
        if not self._view_flags.visible:
            return

        painter = ctx.painter
        sx, sy = self._source_anchor
        tx, ty = self._target_anchor
        ux, uy, length = self._unit_direction()
        if length <= 1e-6:
            return

        stroke = QColor(self._color)

        # Apply ghosted opacity if needed
        if self._view_flags.ghosted:
            stroke.setAlphaF(LINK_GHOST_ALPHA)

        if self._selected:
            self._paint_selected_outline(painter, sx, sy, tx, ty)

        pen = QPen(stroke, 1.8)
        pen.setCosmetic(True)
        if self._preview:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(sx, sy, tx, ty)

        arrow_len = 10.0
        arrow_half_w = 5.0
        bx = tx - (ux * arrow_len)
        by = ty - (uy * arrow_len)
        px = -uy
        py = ux
        triangle = QPolygonF(
            [
                QPointF(tx, ty),
                QPointF(bx + (px * arrow_half_w), by + (py * arrow_half_w)),
                QPointF(bx - (px * arrow_half_w), by - (py * arrow_half_w)),
            ]
        )
        if not self._preview:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(stroke)
            painter.drawPolygon(triangle)

        if self._selected and not self._preview:
            self._paint_selected_labels(painter, stroke, ux, uy)

    def _paint_selected_outline(
        self,
        painter,
        sx: float,
        sy: float,
        tx: float,
        ty: float,
    ) -> None:
        # Use theme token for active selected overlay, fallback to pale white
        overlay_color = NODE_ACTIVE_SELECTED_STROKE_COLOR if self._active_selected else "#f2f5fa"
        white_pen = QPen(QColor(overlay_color), 4.4)
        white_pen.setCosmetic(True)
        yellow_pen = QPen(
            QColor(NODE_SELECTED_STROKE_COLOR),
            4.2 if self._active_selected else 3.0,
        )
        yellow_pen.setCosmetic(True)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(white_pen)
        painter.drawLine(sx, sy, tx, ty)
        painter.setPen(yellow_pen)
        painter.drawLine(sx, sy, tx, ty)

    def _paint_selected_labels(
        self,
        painter,
        stroke: QColor,
        ux: float,
        uy: float,
    ) -> None:
        source_label_x, source_label_y, target_label_x, target_label_y = self._label_positions(
            ux,
            uy,
        )

        painter.save()
        pen = QPen(stroke, 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)

        if self._outgoing_label:
            painter.save()
            painter.translate(source_label_x, source_label_y)
            painter.scale(1.0, -1.0)
            painter.drawText(0.0, 0.0, self._outgoing_label)
            painter.restore()

        if self._incoming_label:
            painter.save()
            painter.translate(target_label_x, target_label_y)
            painter.scale(1.0, -1.0)
            painter.drawText(0.0, 0.0, self._incoming_label)
            painter.restore()

        painter.restore()

    def _unit_direction(self) -> tuple[float, float, float]:
        sx, sy = self._source_anchor
        tx, ty = self._target_anchor
        dx = tx - sx
        dy = ty - sy
        length = sqrt((dx * dx) + (dy * dy))
        if length <= 1e-6:
            return (0.0, 0.0, 0.0)
        return (dx / length, dy / length, length)

    def _label_positions(
        self,
        ux: float,
        uy: float,
    ) -> tuple[float, float, float, float]:
        sx, sy = self._source_anchor
        tx, ty = self._target_anchor
        _ux, _uy, length = self._unit_direction()
        if length <= 1e-6:
            return sx, sy, tx, ty

        px = -uy
        py = ux

        # Inset labels from each endpoint toward the edge interior so they
        # remain away from node bodies while still visually attached to the link.
        along = max(36.0, min(112.0, length * 0.25))
        normal = max(12.0, min(28.0, length * 0.065))

        source_label_x = sx + (ux * along) + (px * normal)
        source_label_y = sy + (uy * along) + (py * normal)
        target_label_x = tx - (ux * along) - (px * normal)
        target_label_y = ty - (uy * along) - (py * normal)
        return source_label_x, source_label_y, target_label_x, target_label_y


__all__ = ["QKnowledgeGraphLinkCanvasItem"]
