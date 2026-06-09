"""Canvas2D knowledge graph node built on :class:`CanvasNodeObjectPixmap`."""
from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import QApplication, QWidget

from lks_utils.gui_qt.canvas2d.interaction.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
from lks_utils.gui_qt.canvas2d.canvas_objects import (
    CanvasNodeHeaderSpec,
    CanvasNodeObjectPixmap,
)
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
    CapabilityHostObject,
)
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_node import (
    DEFAULT_HEADER_HEIGHT_WORLD,
)
from lks_utils.knowledge.default_theme import (
    NODE_FILL_COLOR,
    NODE_HEADER_BG,
    NODE_HEADER_SEP,
    NODE_STROKE_COLOR,
    NODE_SUBTITLE_TEXT,
    NODE_TEXT_COLOR,
)
from lks_utils.knowledge.ui.widgets.graph_node_row_layout import (
    ROW_HEIGHT_WORLD,
    visible_layouts,
)
from lks_utils.knowledge.ui.widgets.graph_node_types import (
    GraphNodeFieldRow,
    GraphNodeValidationSummary,
)
from lks_utils.knowledge.ui.widgets.graph_node_widget import QKnowledgeGraphNodeWidget
from lks_utils.spatial.aabb import AABB


def _make_header_spec(
    *,
    title: str,
    subtitle: str | None,
    header_bg_color: str,
) -> CanvasNodeHeaderSpec:
    return CanvasNodeHeaderSpec(
        title=title,
        subtitle=subtitle,
        background_color=QColor(header_bg_color),
        title_color=QColor(NODE_TEXT_COLOR),
        subtitle_color=QColor(NODE_SUBTITLE_TEXT),
        separator_color=QColor(NODE_HEADER_SEP),
        stroke_color=QColor(NODE_STROKE_COLOR),
        fill_color=QColor(NODE_FILL_COLOR),
        title_font_px=12,
        subtitle_font_px=10,
    )


class QKnowledgeGraphNodeCanvasObject(CanvasNodeObjectPixmap):
    """Knowledge graph node card using generic canvas node chrome."""

    manages_own_selection_highlight: bool = True
    _ROW_HEIGHT_WORLD: float = ROW_HEIGHT_WORLD

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
        on_select: Callable[["QKnowledgeGraphNodeCanvasObject"], None] | None = None,
        on_clear: Callable[[str], None] | None = None,
        on_moved: Callable[[str], None] | None = None,
    ) -> None:
        self._node_widget = QKnowledgeGraphNodeWidget(body_only=False)
        host_rect = QRectF(x, y, width, height)
        super().__init__(
            self._node_widget,
            host_rect,
            header=_make_header_spec(
                title=title,
                subtitle=subtitle,
                header_bg_color=header_bg_color or NODE_HEADER_BG,
            ),
        )
        self.node_id = node_id
        self.title = title
        self.subtitle = subtitle
        self._rows = list(rows)
        self._max_visible_rows = max(1, int(max_visible_rows))
        self._scroll_offset_rows = 0
        self._frontier_hidden = False
        self._on_select = on_select
        self._on_clear = on_clear
        self._on_moved = on_moved
        self._validation_warning_count = 0
        self._validation_error_count = 0
        self._validation_tooltip_text = ""
        self._cached_selection_visual_state: tuple[bool, bool] | None = None
        self._sync_widget()

    @property
    def widget(self) -> QKnowledgeGraphNodeWidget:
        return self._node_widget

    @property
    def header_trailing(self) -> QWidget:
        """Header chrome host for tests and badge lookup."""
        return self._node_widget._header

    def configure_actions(
        self,
        *,
        on_save=None,
        on_revert=None,
        on_remove=None,
        on_delete=None,
        is_save_dirty=None,
    ) -> None:
        _ = (on_save, on_revert, is_save_dirty)
        self._on_clear = on_remove or on_delete
        self._sync_widget()
        self.invalidate_content_pixmap()

    def on_drag(self, world_delta: tuple[float, float]) -> None:
        old_bounds = self.bounds()
        host = self.host_rect
        next_rect = QRectF(
            host.left() + world_delta[0],
            host.top() + world_delta[1],
            host.width(),
            host.height(),
        )
        self.set_host_rect(next_rect)
        self.request_repaint(old_bounds.union(self.bounds()))
        if self._on_moved is not None:
            self._on_moved(self.node_id)

    def set_frontier_hidden(self, hidden: bool) -> None:
        if self._frontier_hidden == hidden:
            return
        self._frontier_hidden = hidden
        self.request_repaint(self.bounds())

    def is_visible(self, viewport_aabb: AABB) -> bool:
        if self._frontier_hidden:
            return False
        return super().is_visible(viewport_aabb)

    def hit_test(self, world_pt: tuple[float, float]) -> bool:
        if self._frontier_hidden:
            return False
        return super().hit_test(world_pt)

    @property
    def header_bg_color(self) -> str:
        return self.header.background_color.name()

    @property
    def selected(self) -> bool:
        selection = self.selection_model()
        return selection.is_selected(self) if selection is not None else False

    @property
    def active_selected(self) -> bool:
        selection = self.selection_model()
        return selection.active_object() is self if selection is not None else False

    def sync_selection_visuals(self) -> None:
        """Track selection state without resyncing the pixmap-backed widget tree."""
        selection = self.selection_model()
        if selection is None:
            state = (False, False)
        else:
            state = (
                selection.is_selected(self),
                selection.active_object() is self,
            )
        if self._cached_selection_visual_state == state:
            return
        self._cached_selection_visual_state = state

    def set_scroll_offset_rows(self, offset: int) -> None:
        max_offset = max(0, len(self._rows) - 1)
        next_offset = min(max(0, int(offset)), max_offset)
        if next_offset == self._scroll_offset_rows:
            return
        self._scroll_offset_rows = next_offset
        self._sync_widget()
        self.invalidate_content_pixmap()

    def visible_rows(self) -> list[GraphNodeFieldRow]:
        return [layout.row for layout in self._visible_layouts()]

    def link_anchor_toward(self, world_target: tuple[float, float]) -> tuple[float, float]:
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

    def handle_input(self, event: CanvasInputEvent) -> bool:
        if event.phase == "wheel":
            if not self.hit_test(event.world_pos):
                return False
            return super().handle_input(event)

        if event.action.id == CANVAS_PRIMARY.id and event.phase in {"drag", "release"}:
            return CapabilityHostObject.handle_input(self, event)

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
            return True
        return CapabilityHostObject.handle_input(self, event)

    def handle_wheel(self, world_pos: tuple[float, float], delta_y: float) -> bool:
        if not self.hit_test(world_pos):
            return False
        total = len(self._rows)
        visible_count = len(self._visible_layouts())
        if total <= visible_count:
            return False
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
            overflow = max(0, len(self._rows) - len(visible) - self._scroll_offset_rows)
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
        self.invalidate_content_pixmap()

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
        old_bounds = self.bounds()
        self.title = title
        self.subtitle = subtitle
        self._rows = list(rows)
        self._max_visible_rows = max(1, int(max_visible_rows))
        max_scroll = max(0, len(self._rows) - self._max_visible_rows)
        self._scroll_offset_rows = min(self._scroll_offset_rows, max_scroll)
        self.set_header(_make_header_spec(
            title=title,
            subtitle=subtitle,
            header_bg_color=header_bg_color,
        ))
        host = self.host_rect
        self.set_host_rect(QRectF(host.left(), host.bottom(), width, height))
        self._sync_widget()
        self.request_repaint(old_bounds.union(self.bounds()))
        if self._on_moved is not None:
            self._on_moved(self.node_id)

    def header_text_regions(self) -> tuple[QRectF, QRectF, QRectF]:
        self._ensure_widget_layout()
        header = self.header_rect
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
        title_left = header.left() + left_pad
        title_right = subtitle_left - 10.0 if subtitle else clear_rect.left() - 8.0
        title_region = QRectF(
            title_left,
            header.top(),
            max(0.0, title_right - title_left),
            header.height(),
        )
        subtitle_region = QRectF(
            max(title_left, subtitle_left),
            header.top(),
            max(0.0, subtitle_right - max(title_left, subtitle_left)),
            header.height(),
        )
        return (title_region, subtitle_region, clear_rect)

    def _visible_layouts(self, **kwargs):
        host = self.host_rect
        return visible_layouts(
            self._rows,
            host_width=host.width(),
            host_height=host.height(),
            header_height=DEFAULT_HEADER_HEIGHT_WORLD,
            scroll_offset_rows=self._scroll_offset_rows,
            max_visible_rows=self._max_visible_rows,
            **kwargs,
        )

    def _ensure_widget_layout(self) -> None:
        width = max(1, int(math.ceil(self.host_rect.width())))
        height = max(1, int(math.ceil(self.host_rect.height())))
        self._node_widget.resize(width, height)
        layout = self._node_widget.layout()
        if layout is not None:
            layout.activate()

    def _widget_child_world_rect(self, geometry: QRect) -> QRectF:
        if geometry.isNull() or geometry.width() <= 0 or geometry.height() <= 0:
            return QRectF()
        host = self.host_rect
        widget = self._node_widget
        scale_x = host.width() / max(1.0, float(widget.width()))
        scale_y = host.height() / max(1.0, float(widget.height()))
        world_left = host.left() + (geometry.x() * scale_x)
        world_bottom = host.bottom() - ((geometry.y() + geometry.height()) * scale_y)
        return QRectF(
            world_left,
            world_bottom,
            geometry.width() * scale_x,
            geometry.height() * scale_y,
        )

    def _clear_button_rect(self) -> QRectF:
        self._ensure_widget_layout()
        button = self._node_widget._clear_button
        geometry = button.geometry()
        header = self.header_rect
        size = 11.0
        margin = 7.0
        fallback = QRectF(
            header.right() - margin - size,
            header.top() + ((header.height() - size) * 0.5),
            size,
            size,
        )
        if geometry.isNull() or geometry.width() <= 0:
            return fallback
        mapped = self._widget_child_world_rect(geometry)
        if mapped.left() < header.center().x():
            return fallback
        return mapped

    def _validation_badge_rect(self) -> QRectF | None:
        badge_text = self._validation_badge_text()
        if not badge_text:
            return None
        self._ensure_widget_layout()
        badge = self._node_widget._validation_badge
        if badge.isVisible():
            geometry = badge.geometry()
            if not geometry.isNull() and geometry.width() > 0 and geometry.height() > 0:
                return self._widget_child_world_rect(geometry)

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        metrics = QFontMetrics(font)
        width = float(metrics.horizontalAdvance(badge_text) + 12)
        height = max(14.0, float(metrics.height()) + 4.0)
        clear_rect = self._clear_button_rect()
        gap = 4.0
        right = clear_rect.left() - gap
        header = self.header_rect
        top = header.top() + ((header.height() - height) * 0.5)
        return QRectF(right - width, top, width, height)

    def _sync_widget(
        self,
        *,
        selected: bool = False,
        active_selected: bool = False,
    ) -> None:
        def _handle_clear() -> None:
            if self._on_clear is not None:
                self._on_clear(self.node_id)

        self._node_widget.set_on_clear(_handle_clear)
        self._node_widget.sync_from_model(
            title=self.title,
            subtitle=self.subtitle,
            rows=self._rows,
            selected=selected,
            active_selected=active_selected,
            header_bg_color=self.header_bg_color,
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
    "QKnowledgeGraphNodeCanvasObject",
]
