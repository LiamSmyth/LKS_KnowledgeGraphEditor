"""Timeline-style table view for one profiling frame sample."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.frame_sample import FrameSample
from lks_utils.profiling.profile_filter import ProfileFilter


_COLOR_TEXT = QColor(0xCC, 0xCC, 0xCC)
_COLOR_WARN = QColor(0xFF, 0xC1, 0x07, 72)
_COLOR_SLOW = QColor(0xEF, 0x53, 0x50, 82)
_COLOR_ROOT = QColor(0x63, 0x81, 0x96, 60)


@dataclass(frozen=True, slots=True)
class _TimelineRow:
    name: str
    start_ms: float
    total_ms: float
    self_ms: float
    depth: int
    device: str


class QProfileTimelineWidget(QWidget):
    """Table-backed timeline summary for one selected profiling frame."""

    block_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._budget_ms: float = 16.6
        self._sample: FrameSample | None = None
        self._filter: ProfileFilter = ProfileFilter()
        self._rows: list[_TimelineRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._table = QTableWidget(0, 6, self)
        self._table.setHorizontalHeaderLabels(
            ["Name", "Start", "Total", "Self", "Depth", "Device"]
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setFont(QFont("Consolas", 9))

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 6):
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)

        self._table.itemSelectionChanged.connect(
            self._on_item_selection_changed)
        layout.addWidget(self._table)

    def set_budget_ms(self, budget_ms: float) -> None:
        self._budget_ms = max(0.1, float(budget_ms))
        if self._sample is not None:
            self.set_frame_sample(self._sample)

    def set_filter(self, f: ProfileFilter) -> None:
        """Apply *f* to visible rows; rebuilds the table immediately."""
        self._filter = f
        if self._sample is not None:
            self.set_frame_sample(self._sample)

    def set_frame_sample(self, sample: FrameSample | None) -> None:
        self._sample = sample
        self._rows.clear()
        self._table.setRowCount(0)
        if sample is None:
            return

        self._collect_rows(sample.call_tree, depth=0, start_ms=0.0)
        self._table.setRowCount(len(self._rows))

        for row_idx, row in enumerate(self._rows):
            indent = "  " * row.depth
            items = [
                QTableWidgetItem(f"{indent}{row.name}"),
                QTableWidgetItem(f"{row.start_ms:.3f}"),
                QTableWidgetItem(f"{row.total_ms:.3f}"),
                QTableWidgetItem(f"{row.self_ms:.3f}"),
                QTableWidgetItem(str(row.depth)),
                QTableWidgetItem(row.device),
            ]

            background = self._row_background(row)
            for col_idx, item in enumerate(items):
                item.setForeground(_COLOR_TEXT)
                if background is not None:
                    item.setBackground(background)
                align = Qt.AlignmentFlag.AlignVCenter
                if col_idx >= 1:
                    align |= Qt.AlignmentFlag.AlignRight
                else:
                    align |= Qt.AlignmentFlag.AlignLeft
                item.setTextAlignment(align)
                self._table.setItem(row_idx, col_idx, item)

    def select_first_by_name(self, node_name: str) -> bool:
        target = node_name.strip()
        for row_idx, row in enumerate(self._rows):
            if row.name == target:
                self._table.selectRow(row_idx)
                return True
        return False

    def _collect_rows(self, node: CallNode, *, depth: int, start_ms: float) -> None:
        row = _TimelineRow(
            name=node.name,
            start_ms=max(0.0, float(start_ms)),
            total_ms=max(0.0, node.total_ms_value),
            self_ms=max(0.0, float(node.self_ms)),
            depth=max(0, int(depth)),
            device=node.device.value.upper(),
        )
        if self._filter.is_empty() or self._filter.matches_subtree(node):
            self._rows.append(row)

        cursor = start_ms + row.self_ms
        for child in node.children:
            self._collect_rows(child, depth=depth + 1, start_ms=cursor)
            cursor += child.total_ms_value

    def _row_background(self, row: _TimelineRow) -> QColor | None:
        if row.depth == 0:
            return _COLOR_ROOT
        ratio = row.total_ms / max(self._budget_ms, 1e-6)
        if ratio >= 1.0:
            return _COLOR_SLOW
        if ratio >= 0.8:
            return _COLOR_WARN
        return None

    def _on_item_selection_changed(self) -> None:
        row_idx = self._table.currentRow()
        if row_idx < 0 or row_idx >= len(self._rows):
            return
        self.block_selected.emit(self._rows[row_idx].name)


__all__ = ["QProfileTimelineWidget"]
