"""Canvas2D graph node primitive used for pre-integration visual modeling."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPen
from PySide6.QtWidgets import QApplication, QLabel

from lks_utils.gui_qt.canvas2d.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.canvas_input_event import CanvasInputEvent
from lks_utils.gui_qt.canvas2d.canvas_pixmap_widget_item import CanvasPixmapWidgetItem
from lks_utils.gui_qt.canvas2d.canvas_paint_context import CanvasPaintContext
from lks_utils.gui_qt.widgets.canvas_table_rows_painter import (
    CanvasTableCellStyle,
    CanvasTableColumn,
    CanvasTableRowsPainter,
)
from lks_utils.knowledge.default_theme import (
    FIELD_LABEL_COLOR,
    NODE_ACTIVE_SELECTED_STROKE_COLOR,
    NODE_CLEAR_BTN_STROKE,
    NODE_FILL_COLOR,
    NODE_HEADER_BG,
    NODE_HEADER_SEP,
    NODE_LITERAL_VALUE_TEXT,
    NODE_REF_VALUE_TEXT,
    NODE_ROW_SEP,
    NODE_ROWS_PANEL_BG,
    NODE_ROWS_PANEL_BORDER,
    NODE_SCROLLBAR_THUMB,
    NODE_SCROLLBAR_TRACK,
    NODE_SELECTED_STROKE_COLOR,
    NODE_STROKE_COLOR,
    NODE_SUBTITLE_TEXT,
    NODE_TEXT_COLOR,
    NODE_TYPE_TEXT,
)
from lks_utils.spatial.aabb import AABB
from lks_utils.knowledge.ui.widgets.graph_node_widget import QKnowledgeGraphNodeWidget


@dataclass(frozen=True, slots=True)
class GraphNodeFieldRow:
    """Display row for the node body primitive."""

    label: str
    value_type: str
    value: str
    value_kind: str = "plain"


@dataclass(frozen=True, slots=True)
class GraphNodeValidationSummary:
    """Compiled validation summary for a graph node badge and tooltip."""

    warning_count: int = 0
    error_count: int = 0
    tooltip_text: str = ""


@dataclass(frozen=True, slots=True)
class _GraphNodeVisibleLayout:
    row: GraphNodeFieldRow
    height: float
    multiline_value: bool
    visible_lines: int


class QKnowledgeGraphNodeCanvasItem(CanvasPixmapWidgetItem):
    """Compact graph node primitive with overflow windowing and clear action."""

    manages_own_selection_highlight: bool = True

    _HEADER_HEIGHT_WORLD: float = 21.0
    _PADDING_WORLD: float = 8.0
    _ROW_HEIGHT_WORLD: float = 20.0
    _MULTILINE_MIN_LINES: int = 3
    _MULTILINE_MAX_LINES: int = 3
    _MULTILINE_ROW_PADDING_WORLD: float = 6.0
    _STRING_WRAP_TRIGGER_CHARS: int = 36
    _LABEL_COL_WIDTH_WORLD: float = 64.0
    _TYPE_COL_WIDTH_WORLD: float = 52.0
    _ACTION_WIDTH_WORLD: float = 11.0
    _ACTION_HEIGHT_WORLD: float = 11.0
    _ACTION_MARGIN_WORLD: float = 7.0

    def __init__(
        self,
        *,
        node_id: str,
        title: str,
        subtitle: str | None,
        x: float,
        y: float,
        width: float,
        height: float,
        rows: list[GraphNodeFieldRow],
        max_visible_rows: int = 5,
        header_bg_color: str | None = None,
        on_select: Callable[[QKnowledgeGraphNodeCanvasItem],
                            None] | None = None,
        on_clear: Callable[[str], None] | None = None,
        on_moved: Callable[[str], None] | None = None,
    ) -> None:
        self._node_widget = QKnowledgeGraphNodeWidget()
        super().__init__(self._node_widget, QRectF(x, y, width, height))
        self.node_id = node_id
        self.title = title
        self.subtitle = subtitle
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._rows = list(rows)
        self._max_visible_rows = max(1, int(max_visible_rows))
        self._scroll_offset_rows = 0
        self._header_bg_color = header_bg_color or NODE_HEADER_BG
        self._selected = False
        self._active_selected = False
        self._frontier_hidden = False
        self._on_select = on_select
        self._on_clear = on_clear
        self._on_moved = on_moved
        self._validation_warning_count = 0
        self._validation_error_count = 0
        self._validation_tooltip_text = ""
        self._rows_painter = CanvasTableRowsPainter(
            row_height=self._ROW_HEIGHT_WORLD,
            font_px=11,
            separator_color=QColor(NODE_ROW_SEP),
        )
        self._sync_widget()

    def configure_actions(
        self,
        *,
        on_save=None,
        on_revert=None,
        on_remove=None,
        on_delete=None,
        is_save_dirty=None,
    ) -> None:
        """Compatibility adapter for legacy graph-tab action wiring."""
        _ = (on_save, on_revert, is_save_dirty)
        self._on_clear = on_remove or on_delete
        self._sync_widget()
        self.invalidate()

    def on_drag(self, world_delta: tuple[float, float]) -> None:
        """Move this node by *world_delta* while preserving repaint bounds."""
        old_bounds = self.bounds()
        self._x += world_delta[0]
        self._y += world_delta[1]
        self.set_world_rect(
            QRectF(self._x, self._y, self._width, self._height))
        self.request_repaint(old_bounds.union(self.bounds()))
        # Notify that this node has moved so connected links can update
        if self._on_moved is not None:
            self._on_moved(self.node_id)

    def bounds(self) -> AABB:
        return AABB(self._x, self._y, self._x + self._width, self._y + self._height)

    def set_frontier_hidden(self, hidden: bool) -> None:
        """Hide or show this node based on frontier-traversal filtering.

        When hidden, the node is neither drawn nor hit-testable.
        Called by graph_canvas when link-type view state changes.
        """
        if self._frontier_hidden == hidden:
            return
        self._frontier_hidden = hidden
        self.request_repaint(self.bounds())

    def is_visible(self, viewport_aabb: AABB) -> bool:
        """Return False when frontier-hidden, otherwise delegate to base."""
        if self._frontier_hidden:
            return False
        return super().is_visible(viewport_aabb)

    def hit_test(self, world_pt: tuple[float, float]) -> bool:
        """Return False when frontier-hidden, otherwise use bounds containment."""
        if self._frontier_hidden:
            return False
        b = self.bounds()
        return b.contains_point(world_pt[0], world_pt[1])

    @property
    def selected(self) -> bool:
        """Return selected state."""
        return self._selected

    @property
    def header_bg_color(self) -> str:
        """Resolved header background color used for this card."""
        return self._header_bg_color

    @property
    def active_selected(self) -> bool:
        """Return whether this selected card is the active selection."""
        return self._active_selected

    @active_selected.setter
    def active_selected(self, value: bool) -> None:
        if self._active_selected == value:
            return
        self._active_selected = value
        self.invalidate()

    @selected.setter
    def selected(self, value: bool) -> None:
        if self._selected == value:
            return
        self._selected = value
        self.invalidate()

    def set_scroll_offset_rows(self, offset: int) -> None:
        """Adjust the visible row window start for overflow cases."""
        max_offset = max(0, len(self._rows) - 1)
        next_offset = min(max(0, int(offset)), max_offset)
        if next_offset == self._scroll_offset_rows:
            return
        self._scroll_offset_rows = next_offset
        self._sync_widget()
        self.invalidate()

    def visible_rows(self) -> list[GraphNodeFieldRow]:
        """Return the currently visible body rows."""
        return [layout.row for layout in self._visible_layouts()]

    def link_anchor_toward(self, world_target: tuple[float, float]) -> tuple[float, float]:
        """Return the border anchor where a center-target line exits this card."""
        bounds = self.bounds()
        cx = bounds.cx
        cy = bounds.cy
        tx, ty = world_target
        dx = tx - cx
        dy = ty - cy
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            return (cx, cy)

        half_w = bounds.width * 0.5
        half_h = bounds.height * 0.5
        scale_x = half_w / abs(dx) if abs(dx) > 1e-6 else float("inf")
        scale_y = half_h / abs(dy) if abs(dy) > 1e-6 else float("inf")
        scale = min(scale_x, scale_y)
        return (cx + (dx * scale), cy + (dy * scale))

    def paint(self, ctx: CanvasPaintContext) -> None:
        super().paint(ctx)
        if not (self._selected or self._active_selected):
            return
        painter = ctx.painter
        rect = self.bounds()

        if self._active_selected:
            # Render dual-outline for active selection:
            # 1. Base selected outline (yellow)
            # 2. Thicker pale/white overlay outline on top

            # First pass: selected outline (yellow, thinner)
            pen = QPen(QColor(NODE_SELECTED_STROKE_COLOR), 2.0)
            pen.setCosmetic(True)
            painter.save()
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                rect.x0, rect.y0, rect.width, rect.height, 4.0, 4.0)
            painter.restore()

            # Second pass: active overlay (pale white, thicker)
            pen = QPen(QColor(NODE_ACTIVE_SELECTED_STROKE_COLOR), 3.2)
            pen.setCosmetic(True)
            painter.save()
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                rect.x0, rect.y0, rect.width, rect.height, 4.0, 4.0)
            painter.restore()
        else:
            # Standard selected outline (yellow only)
            pen = QPen(QColor(NODE_SELECTED_STROKE_COLOR), 2.0)
            pen.setCosmetic(True)
            painter.save()
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                rect.x0, rect.y0, rect.width, rect.height, 4.0, 4.0)
            painter.restore()

    def _paint_legacy(self, ctx: CanvasPaintContext) -> None:
        painter = ctx.painter
        rect = self.bounds()

        base_pen = QPen(QColor(NODE_STROKE_COLOR), 1.4)
        base_pen.setCosmetic(True)
        painter.setPen(base_pen)
        painter.setBrush(QColor(NODE_FILL_COLOR))
        painter.drawRoundedRect(
            rect.x0, rect.y0, rect.width, rect.height, 4.0, 4.0)

        stroke_color = QColor(
            NODE_SELECTED_STROKE_COLOR if self._selected else NODE_STROKE_COLOR)
        stroke_width = 3.2 if self._active_selected else 2.4 if self._selected else 1.4
        pen = QPen(stroke_color, stroke_width)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.x0, rect.y0, rect.width, rect.height, 4.0, 4.0)

        painter.save()
        painter.setClipRect(rect.x0 + 1.0, rect.y0 + 1.0,
                            rect.width - 2.0, rect.height - 2.0)
        self._paint_header(ctx, rect)
        self._paint_clear_button(ctx)
        self._paint_rows_panel(ctx)
        self._paint_rows(ctx)
        self._paint_overflow_scrollbar(ctx)
        painter.restore()

    def handle_input(self, event: CanvasInputEvent) -> bool:
        if event.phase == "wheel":
            return super().handle_input(event)
        if event.action.id != CANVAS_PRIMARY.id or event.phase != "press":
            return False
        if not self.hit_test(event.world_pos):
            return False
        wx, wy = event.world_pos
        badge_rect = self._validation_badge_rect()
        if badge_rect is not None and badge_rect.contains(wx, wy):
            tooltip = self._validation_tooltip_text.strip()
            if tooltip:
                QApplication.clipboard().setText(tooltip)
                return True
        clear_rect = self._clear_button_rect()
        if clear_rect.contains(wx, wy):
            if self._on_clear is not None:
                self._on_clear(self.node_id)
            return True
        if self._on_select is not None:
            self._on_select(self)
        # Let the canvas own drag composition for draggable items.
        return False

    def handle_wheel(self, world_pos: tuple[float, float], delta_y: float) -> bool:
        """Scroll node rows on wheel when cursor is over this node."""
        if not self.hit_test(world_pos):
            return False
        total = len(self._rows)
        visible_count = len(self._visible_layouts())
        if total <= visible_count:
            return False
        # delta_y > 0 = wheel up = scroll toward first rows (decrease offset)
        step = 1 if delta_y < 0 else -1
        new_offset = max(0, min(total - 1, self._scroll_offset_rows + step))
        self.set_scroll_offset_rows(new_offset)
        return True

    def tooltip_at(self, world_pt: tuple[float, float]) -> str | None:
        if not self.hit_test(world_pt):
            return None
        wx, wy = world_pt
        if self._clear_button_rect().contains(wx, wy):
            return "Remove from graph"
        lines = [self.title]
        if self.subtitle:
            lines.append(self.subtitle)
        if self._validation_tooltip_text:
            lines.append("")
            lines.extend(self._validation_tooltip_text.splitlines())
        else:
            visible = self.visible_rows()
            overflow = max(0, len(self._rows) - len(visible) -
                           self._scroll_offset_rows)
            if overflow > 0:
                lines.append(f"+{overflow} more rows")
        return "\n".join(lines)

    def set_validation_issues(
        self,
        *,
        warning_count: int,
        error_count: int,
        tooltip_text: str = "",
    ) -> None:
        warning_count = max(0, int(warning_count))
        error_count = max(0, int(error_count))
        tooltip_text = tooltip_text.strip()
        if (
            warning_count == self._validation_warning_count
            and error_count == self._validation_error_count
            and tooltip_text == self._validation_tooltip_text
        ):
            return
        self._validation_warning_count = warning_count
        self._validation_error_count = error_count
        self._validation_tooltip_text = tooltip_text
        self._sync_widget()
        self.invalidate()

    def update_render_model(
        self,
        *,
        title: str,
        subtitle: str | None,
        width: float,
        height: float,
        rows: list[GraphNodeFieldRow],
        max_visible_rows: int,
        header_bg_color: str,
    ) -> None:
        """Refresh the rendered node card in place without replacing the item."""
        old_bounds = self.bounds()
        self.title = title
        self.subtitle = subtitle
        self._rows = list(rows)
        self._max_visible_rows = max(1, int(max_visible_rows))
        self._header_bg_color = header_bg_color
        self._width = width
        self._height = height
        max_scroll = max(0, len(self._rows) - self._max_visible_rows)
        self._scroll_offset_rows = min(self._scroll_offset_rows, max_scroll)
        self.set_world_rect(
            QRectF(self._x, self._y, self._width, self._height))
        self._sync_widget()
        self.request_repaint(old_bounds.union(self.bounds()))
        if self._on_moved is not None:
            self._on_moved(self.node_id)

    def _paint_header(self, ctx: CanvasPaintContext, rect: AABB) -> None:
        painter = ctx.painter
        header_rect = QRectF(
            rect.x0 + 1.0,
            rect.y1 - self._HEADER_HEIGHT_WORLD - 1.0,
            rect.width - 2.0,
            self._HEADER_HEIGHT_WORLD,
        )
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._header_bg_color))
        painter.drawRect(header_rect)
        sep_pen = QPen(QColor(NODE_HEADER_SEP), 1.0)
        sep_pen.setCosmetic(True)
        painter.setPen(sep_pen)
        painter.drawLine(header_rect.left(), header_rect.bottom(),
                         header_rect.right(), header_rect.bottom())
        painter.restore()

        left_pad = 8.0
        right_gap = 8.0
        title_font = QFont()
        title_font.setPixelSize(12)
        subtitle_font = QFont()
        subtitle_font.setPixelSize(10)
        subtitle_font.setItalic(True)
        title_metrics = QFontMetrics(title_font)
        subtitle_metrics = QFontMetrics(subtitle_font)
        subtitle = self.subtitle or ""

        clear_rect = self._clear_button_rect()
        subtitle_right = clear_rect.left() - right_gap
        subtitle_width = float(max(
            subtitle_metrics.horizontalAdvance(subtitle),
            subtitle_metrics.tightBoundingRect(subtitle).width(),
        )) if subtitle else 0.0
        subtitle_left = subtitle_right - subtitle_width
        title_left = header_rect.left() + left_pad
        title_right_limit = subtitle_left - 10.0 if subtitle else clear_rect.left() - \
            8.0
        title_width = max(12.0, title_right_limit - title_left)
        text_slot_top = header_rect.top() + 1.0
        text_slot_height = max(8.0, header_rect.height() - 2.0)
        title_rect = QRectF(
            title_left,
            text_slot_top,
            title_width,
            text_slot_height,
        )
        elided_title = title_metrics.elidedText(
            self.title,
            Qt.TextElideMode.ElideRight,
            int(max(1.0, title_rect.width())),
        )
        painter.save()
        painter.setClipRect(title_rect, Qt.ClipOperation.IntersectClip)
        painter.translate(title_rect.left(), title_rect.bottom())
        painter.scale(1.0, -1.0)
        painter.setFont(title_font)
        painter.setPen(QColor(NODE_TEXT_COLOR))
        painter.drawText(
            QRectF(0.0, 0.0, title_rect.width(), title_rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_title,
        )
        painter.restore()

        if subtitle:
            subtitle_left = max(subtitle_left, title_left + 12.0)
            # Reserve a tiny horizontal inset so italic glyph overhang does not
            # get hard-clipped at the left edge of the subtitle slot.
            subtitle_inset = 2.0
            subtitle_rect = QRectF(
                subtitle_left - subtitle_inset,
                text_slot_top,
                max(8.0, (subtitle_right - subtitle_left) + subtitle_inset),
                text_slot_height,
            )
            painter.save()
            painter.setClipRect(subtitle_rect, Qt.ClipOperation.IntersectClip)
            painter.translate(subtitle_rect.left(), subtitle_rect.bottom())
            painter.scale(1.0, -1.0)
            painter.setFont(subtitle_font)
            painter.setPen(QColor(NODE_SUBTITLE_TEXT))
            fitted_subtitle = subtitle_metrics.elidedText(
                subtitle,
                Qt.TextElideMode.ElideRight,
                int(max(1.0, subtitle_rect.width())),
            )
            painter.drawText(
                QRectF(0.0, 0.0, subtitle_rect.width(),
                       subtitle_rect.height()),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                fitted_subtitle,
            )
            painter.restore()

    def header_text_regions(self) -> tuple[QRectF, QRectF, QRectF]:
        """Return title, subtitle, and clear-button regions for overlap tests."""
        rect = self.bounds()
        clear_rect = self._clear_button_rect()
        left_pad = 8.0
        right_gap = 8.0
        subtitle_font = QFont()
        subtitle_font.setPixelSize(10)
        subtitle_font.setItalic(True)
        subtitle_metrics = QFontMetrics(subtitle_font)
        subtitle = self.subtitle or ""
        subtitle_w = float(max(
            subtitle_metrics.horizontalAdvance(subtitle),
            subtitle_metrics.tightBoundingRect(subtitle).width(),
        )) if subtitle else 0.0

        subtitle_right = clear_rect.left() - right_gap
        subtitle_left = subtitle_right - subtitle_w
        title_left = rect.x0 + 1.0 + left_pad
        title_right = subtitle_left - 10.0 if subtitle else clear_rect.left() - 8.0
        title_region = QRectF(title_left, rect.y1 - self._HEADER_HEIGHT_WORLD -
                              1.0, max(0.0, title_right - title_left), self._HEADER_HEIGHT_WORLD)
        subtitle_region = QRectF(max(title_left, subtitle_left), rect.y1 - self._HEADER_HEIGHT_WORLD - 1.0, max(
            0.0, subtitle_right - max(title_left, subtitle_left)), self._HEADER_HEIGHT_WORLD)
        return (title_region, subtitle_region, clear_rect)

    def _paint_clear_button(self, ctx: CanvasPaintContext) -> None:
        painter = ctx.painter
        rect = self._clear_button_rect()
        painter.save()
        painter.setPen(QPen(QColor(NODE_CLEAR_BTN_STROKE), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        inset = 2.0
        painter.drawLine(rect.left() + inset, rect.top() + inset,
                         rect.right() - inset, rect.bottom() - inset)
        painter.drawLine(rect.left() + inset, rect.bottom() -
                         inset, rect.right() - inset, rect.top() + inset)
        painter.restore()

    def _paint_rows_panel(self, ctx: CanvasPaintContext) -> None:
        painter = ctx.painter
        panel = self._rows_panel_rect()
        painter.save()
        painter.setPen(QPen(QColor(NODE_ROWS_PANEL_BORDER), 1.0))
        painter.setBrush(QColor(NODE_ROWS_PANEL_BG))
        painter.drawRoundedRect(panel, 3.0, 3.0)
        painter.restore()

    def _paint_rows(self, ctx: CanvasPaintContext) -> None:
        rect = self.bounds()
        panel = self._rows_panel_rect()

        label_w = max(32.0, self._LABEL_COL_WIDTH_WORLD)
        type_w = max(40.0, self._TYPE_COL_WIDTH_WORLD)
        value_w = max(20.0, rect.width -
                      (self._PADDING_WORLD * 2.0) - label_w - type_w)

        visible_layouts = self._visible_layouts(scrollbar_inset=0.0)
        total = len(self._rows)
        visible_count = len(visible_layouts)
        has_overflow = total > visible_count and total > 0
        scrollbar_inset = 7.0 if has_overflow else 0.0
        if has_overflow:
            visible_layouts = self._visible_layouts(
                scrollbar_inset=scrollbar_inset)

        columns = [
            CanvasTableColumn(
                width=label_w,
                color=QColor(FIELD_LABEL_COLOR),
                vertical_align="top",
            ),
            CanvasTableColumn(
                width=type_w,
                color=QColor(NODE_TYPE_TEXT),
                vertical_align="top",
            ),
            CanvasTableColumn(width=value_w - scrollbar_inset,
                              color=QColor(NODE_TEXT_COLOR)),
        ]

        rows_data = [
            (layout.row.label, f"({layout.row.value_type})", layout.row.value)
            for layout in visible_layouts
        ]
        row_heights = [layout.height for layout in visible_layouts]
        cell_styles = {
            (index, 2): CanvasTableCellStyle(
                multiline=layout.multiline_value,
                max_lines=layout.visible_lines if layout.multiline_value else None,
                text_color=(
                    QColor(NODE_REF_VALUE_TEXT)
                    if layout.row.value_kind == "reference"
                    else QColor(NODE_LITERAL_VALUE_TEXT)
                    if layout.row.value_kind == "literal"
                    else None
                ),
            )
            for index, layout in enumerate(visible_layouts)
            if layout.multiline_value or layout.row.value_kind != "plain"
        }

        self._rows_painter.paint_rows(
            ctx,
            panel_rect=panel,
            columns=columns,
            rows=rows_data,
            first_row_top=panel.bottom() - 2.0,
            row_heights=row_heights,
            cell_styles=cell_styles,
        )

    def _paint_overflow_scrollbar(self, ctx: CanvasPaintContext) -> None:
        if not self._rows:
            return

        row_heights = self._row_heights_for_panel(scrollbar_inset=0.0)
        visible_layouts = self._visible_layouts(
            row_heights=row_heights,
            scrollbar_inset=0.0,
        )
        visible_height = sum(layout.height for layout in visible_layouts)
        content_height = sum(row_heights)
        viewport_height = max(1.0, self._rows_panel_rect().height() - 4.0)
        if content_height <= viewport_height or not visible_layouts:
            return

        # Recompute with reserved scrollbar space so wrapping and visible-line
        # geometry match the actual painted content width.
        row_heights = self._row_heights_for_panel(scrollbar_inset=7.0)
        visible_layouts = self._visible_layouts(
            row_heights=row_heights,
            scrollbar_inset=7.0,
        )
        visible_height = sum(layout.height for layout in visible_layouts)
        content_height = sum(row_heights)

        painter = ctx.painter
        panel = self._rows_panel_rect()
        track_h = max(8.0, panel.height() - 4.0)
        track = QRectF(panel.right() - 5.0, panel.top() + 2.0, 3.5, track_h)

        thumb_ratio = min(1.0, visible_height / float(content_height))
        thumb_h = max(10.0, track_h * thumb_ratio)
        scroll_offset_height = sum(row_heights[:self._scroll_offset_rows])
        max_offset_height = max(1.0, content_height - viewport_height)
        t = min(1.0, scroll_offset_height / max_offset_height)
        thumb_y = track.y() + ((track_h - thumb_h) * t)
        thumb = QRectF(track.x(), thumb_y, track.width(), thumb_h)

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(NODE_SCROLLBAR_TRACK))
        painter.drawRoundedRect(track, 1.5, 1.5)
        painter.setBrush(QColor(NODE_SCROLLBAR_THUMB))
        painter.drawRoundedRect(thumb, 1.5, 1.5)
        painter.restore()

    def _rows_panel_rect(self) -> QRectF:
        rect = self.bounds()
        top = rect.y1 - self._HEADER_HEIGHT_WORLD - 3.5
        bottom = rect.y0 + self._PADDING_WORLD
        return QRectF(
            rect.x0 + self._PADDING_WORLD,
            bottom,
            rect.width - (self._PADDING_WORLD * 2.0),
            max(8.0, top - bottom),
        )

    def _clear_button_rect(self) -> QRectF:
        rect = self.bounds()
        right = rect.x1 - self._ACTION_MARGIN_WORLD
        top = rect.y1 - self._ACTION_MARGIN_WORLD
        return QRectF(
            right - self._ACTION_WIDTH_WORLD,
            top - self._ACTION_HEIGHT_WORLD,
            self._ACTION_WIDTH_WORLD,
            self._ACTION_HEIGHT_WORLD,
        )

    def _validation_badge_rect(self) -> QRectF | None:
        badge_text = self._validation_badge_text()
        if not badge_text:
            return None
        badge = self.widget.findChild(QLabel, "validation_summary_badge")
        if badge is not None and badge.isVisible():
            geometry = badge.geometry()
            if not geometry.isNull():
                rect = self.bounds()
                return QRectF(
                    rect.x0 + float(geometry.x()),
                    rect.y1 - float(geometry.y() + geometry.height()),
                    float(geometry.width()),
                    float(geometry.height()),
                )

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        metrics = QFontMetrics(font)
        width = float(metrics.horizontalAdvance(badge_text) + 12)
        height = max(14.0, float(metrics.height()) + 4.0)
        clear_rect = self._clear_button_rect()
        gap = 4.0
        right = clear_rect.left() - gap
        top = self.bounds().y1 - self._HEADER_HEIGHT_WORLD + (
            (self._HEADER_HEIGHT_WORLD - height) * 0.5
        )
        return QRectF(
            right - width,
            top,
            width,
            height,
        )

    def _visible_layouts(
        self,
        *,
        row_heights: list[float] | None = None,
        scrollbar_inset: float = 0.0,
    ) -> list[_GraphNodeVisibleLayout]:
        if not self._rows:
            return []
        computed_row_heights = (
            self._row_heights_for_panel(scrollbar_inset=scrollbar_inset)
            if row_heights is None else row_heights
        )
        value_width = self._value_column_width(scrollbar_inset=scrollbar_inset)
        row_metrics = QFontMetrics(self._rows_font())
        panel_height = max(1.0, self._rows_panel_rect().height() - 4.0)
        layouts: list[_GraphNodeVisibleLayout] = []
        consumed = 0.0
        for index in range(self._scroll_offset_rows, len(self._rows)):
            row = self._rows[index]
            row_height = computed_row_heights[index]
            if layouts and consumed + row_height > panel_height:
                break
            layouts.append(
                _GraphNodeVisibleLayout(
                    row=row,
                    height=row_height,
                    multiline_value=row_height > self._ROW_HEIGHT_WORLD,
                    visible_lines=self._visible_line_count_for_row(
                        row,
                        value_width,
                        row_metrics,
                    ),
                )
            )
            consumed += row_height
            if len(layouts) >= self._max_visible_rows:
                break
        return layouts

    def _row_heights_for_panel(self, *, scrollbar_inset: float) -> list[float]:
        value_width = self._value_column_width(scrollbar_inset=scrollbar_inset)
        metrics = QFontMetrics(self._rows_font())
        return [self._row_height_for(row, value_width, metrics) for row in self._rows]

    def _value_column_width(self, *, scrollbar_inset: float) -> float:
        rect = self.bounds()
        label_w = max(32.0, self._LABEL_COL_WIDTH_WORLD)
        type_w = max(40.0, self._TYPE_COL_WIDTH_WORLD)
        value_w = max(20.0, rect.width -
                      (self._PADDING_WORLD * 2.0) - label_w - type_w)
        return max(8.0, value_w - scrollbar_inset - 8.0)

    def _rows_font(self) -> QFont:
        font = QFont()
        font.setPixelSize(11)
        return font

    def _row_height_for(
        self,
        row: GraphNodeFieldRow,
        value_width: float,
        metrics: QFontMetrics,
    ) -> float:
        visible_lines = self._visible_line_count_for_row(
            row, value_width, metrics)
        if visible_lines <= 1:
            return self._ROW_HEIGHT_WORLD
        line_height = max(float(metrics.lineSpacing()),
                          self._ROW_HEIGHT_WORLD - 4.0)
        return max(
            self._ROW_HEIGHT_WORLD,
            (line_height * visible_lines) + self._MULTILINE_ROW_PADDING_WORLD,
        )

    def _visible_line_count_for_row(
        self,
        row: GraphNodeFieldRow,
        value_width: float,
        metrics: QFontMetrics,
    ) -> int:
        if not self._should_wrap_value(row, value_width, metrics):
            return 1
        line_height = max(float(metrics.lineSpacing()),
                          self._ROW_HEIGHT_WORLD - 4.0)
        wrap_rect = metrics.boundingRect(
            QRect(0, 0, max(1, int(value_width)), 4096),
            int(Qt.TextFlag.TextWordWrap),
            row.value,
        )
        estimated_lines = max(
            1, ceil(wrap_rect.height() / max(1.0, line_height)))
        return max(
            self._MULTILINE_MIN_LINES,
            min(self._MULTILINE_MAX_LINES, estimated_lines),
        )

    def _should_wrap_value(
        self,
        row: GraphNodeFieldRow,
        value_width: float,
        metrics: QFontMetrics,
    ) -> bool:
        return metrics.horizontalAdvance(row.value) > int(value_width)

    def _sync_widget(self) -> None:
        def _handle_clear() -> None:
            if self._on_clear is not None:
                self._on_clear(self.node_id)

        self._node_widget.set_on_clear(_handle_clear)
        self._node_widget.sync_from_model(
            title=self.title,
            subtitle=self.subtitle,
            rows=self._rows,
            selected=self._selected,
            active_selected=self._active_selected,
            header_bg_color=self._header_bg_color,
            scroll_offset_rows=self._scroll_offset_rows,
            max_visible_rows=self._max_visible_rows,
            clear_enabled=self._on_clear is not None,
            validation_badge_text=self._validation_badge_text(),
            validation_badge_tooltip=self._validation_tooltip_text,
            validation_badge_kind=self._validation_badge_kind(),
        )

    def _validation_badge_text(self) -> str | None:
        parts: list[str] = []
        if self._validation_warning_count > 0:
            parts.append(f"W{self._validation_warning_count}")
        if self._validation_error_count > 0:
            parts.append(f"E{self._validation_error_count}")
        return " ".join(parts) if parts else None

    def _validation_badge_kind(self) -> str | None:
        if self._validation_error_count > 0 and self._validation_warning_count > 0:
            return "mixed"
        if self._validation_error_count > 0:
            return "error"
        if self._validation_warning_count > 0:
            return "warning"
        return None


__all__ = [
    "GraphNodeFieldRow",
    "GraphNodeValidationSummary",
    "QKnowledgeGraphNodeCanvasItem",
]
