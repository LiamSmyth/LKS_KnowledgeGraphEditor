"""Row layout helpers shared by graph node canvas objects and tests."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QFontMetrics

from lks_utils.knowledge.ui.widgets.graph_node_types import GraphNodeFieldRow


@dataclass(frozen=True, slots=True)
class GraphNodeVisibleLayout:
    row: GraphNodeFieldRow
    height: float
    multiline_value: bool
    visible_lines: int


ROW_HEIGHT_WORLD: float = 20.0
PADDING_WORLD: float = 8.0
LABEL_COL_WIDTH_WORLD: float = 64.0
TYPE_COL_WIDTH_WORLD: float = 52.0
MULTILINE_MIN_LINES: int = 3
MULTILINE_MAX_LINES: int = 3
MULTILINE_ROW_PADDING_WORLD: float = 6.0


def rows_font() -> QFont:
    font = QFont()
    font.setPixelSize(11)
    return font


def value_column_width(*, host_width: float, scrollbar_inset: float) -> float:
    label_w = max(32.0, LABEL_COL_WIDTH_WORLD)
    type_w = max(40.0, TYPE_COL_WIDTH_WORLD)
    value_w = max(20.0, host_width - (PADDING_WORLD * 2.0) - label_w - type_w)
    return max(8.0, value_w - scrollbar_inset - 8.0)


def visible_line_count_for_row(
    row: GraphNodeFieldRow,
    value_width: float,
    metrics: QFontMetrics,
) -> int:
    if metrics.horizontalAdvance(row.value) <= int(value_width):
        return 1
    line_height = max(float(metrics.lineSpacing()), ROW_HEIGHT_WORLD - 4.0)
    wrap_rect = metrics.boundingRect(
        QRect(0, 0, max(1, int(value_width)), 4096),
        int(Qt.TextFlag.TextWordWrap),
        row.value,
    )
    estimated_lines = max(1, ceil(wrap_rect.height() / max(1.0, line_height)))
    return max(MULTILINE_MIN_LINES, min(MULTILINE_MAX_LINES, estimated_lines))


def row_height_for(
    row: GraphNodeFieldRow,
    value_width: float,
    metrics: QFontMetrics,
) -> float:
    visible_lines = visible_line_count_for_row(row, value_width, metrics)
    if visible_lines <= 1:
        return ROW_HEIGHT_WORLD
    line_height = max(float(metrics.lineSpacing()), ROW_HEIGHT_WORLD - 4.0)
    return max(
        ROW_HEIGHT_WORLD,
        (line_height * visible_lines) + MULTILINE_ROW_PADDING_WORLD,
    )


def row_heights_for_panel(
    rows: list[GraphNodeFieldRow],
    *,
    host_width: float,
    scrollbar_inset: float,
) -> list[float]:
    value_width = value_column_width(
        host_width=host_width,
        scrollbar_inset=scrollbar_inset,
    )
    metrics = QFontMetrics(rows_font())
    return [row_height_for(row, value_width, metrics) for row in rows]


def rows_panel_height(*, host_height: float, header_height: float) -> float:
    return max(8.0, host_height - header_height - 3.5 - PADDING_WORLD)


def visible_layouts(
    rows: list[GraphNodeFieldRow],
    *,
    host_width: float,
    host_height: float,
    header_height: float,
    scroll_offset_rows: int,
    max_visible_rows: int,
    row_heights: list[float] | None = None,
    scrollbar_inset: float = 0.0,
) -> list[GraphNodeVisibleLayout]:
    if not rows:
        return []
    computed_row_heights = (
        row_heights_for_panel(
            rows,
            host_width=host_width,
            scrollbar_inset=scrollbar_inset,
        )
        if row_heights is None
        else row_heights
    )
    value_width = value_column_width(
        host_width=host_width,
        scrollbar_inset=scrollbar_inset,
    )
    row_metrics = QFontMetrics(rows_font())
    panel_height = max(1.0, rows_panel_height(
        host_height=host_height,
        header_height=header_height,
    ) - 4.0)
    layouts: list[GraphNodeVisibleLayout] = []
    consumed = 0.0
    for index in range(scroll_offset_rows, len(rows)):
        row = rows[index]
        row_height = computed_row_heights[index]
        if layouts and consumed + row_height > panel_height:
            break
        layouts.append(
            GraphNodeVisibleLayout(
                row=row,
                height=row_height,
                multiline_value=row_height > ROW_HEIGHT_WORLD,
                visible_lines=visible_line_count_for_row(
                    row,
                    value_width,
                    row_metrics,
                ),
            )
        )
        consumed += row_height
        if len(layouts) >= max(1, int(max_visible_rows)):
            break
    return layouts


__all__ = [
    "GraphNodeVisibleLayout",
    "ROW_HEIGHT_WORLD",
    "visible_layouts",
]
