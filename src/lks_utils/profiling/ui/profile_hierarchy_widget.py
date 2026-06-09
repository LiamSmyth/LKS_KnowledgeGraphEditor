"""Hierarchy view for generic profiling frame samples."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
    QVBoxLayout,
    QWidget,
)

from lks_utils.profiling.call_node import CallNode
from lks_utils.profiling.frame_sample import FrameSample
from lks_utils.profiling.profile_filter import ProfileFilter


_COLOR_TEXT = QColor(0xCC, 0xCC, 0xCC)
_COLOR_ROOT = QColor(0x63, 0x81, 0x96, 60)
_COLOR_WARN = QColor(0xFF, 0xC1, 0x07, 72)
_COLOR_SLOW = QColor(0xEF, 0x53, 0x50, 82)


class QProfileHierarchyWidget(QWidget):
    """Tree view of inclusive and self timings for one selected frame."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._budget_ms: float = 16.6
        self._sample: FrameSample | None = None
        self._filter: ProfileFilter = ProfileFilter()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(6)
        self._tree.setHeaderLabels(
            ["Name", "Self", "Total", "%", "Calls", "Device"])
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(False)
        self._tree.setUniformRowHeights(True)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        self._tree.setFont(QFont("Consolas", 9))
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 6):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._tree)

    def set_budget_ms(self, budget_ms: float) -> None:
        self._budget_ms = max(0.1, float(budget_ms))
        if self._sample is not None:
            self.set_frame_sample(self._sample)

    def set_filter(self, f: ProfileFilter) -> None:
        self._filter = f
        if self._sample is not None:
            self.set_frame_sample(self._sample)

    def set_frame_sample(self, sample: FrameSample | None) -> None:
        self._sample = sample
        self._tree.clear()
        if sample is None:
            return
        total_ms = max(sample.call_tree.total_ms_value, 1e-6)
        root_object = self._build_item(
            sample.call_tree, total_ms=total_ms, is_root=True)
        self._tree.addTopLevelItem(root_object)
        root_object.setExpanded(True)
        for idx in range(root_object.childCount()):
            root_object.child(idx).setExpanded(True)

    def select_first_by_name(self, node_name: str) -> bool:
        """Select and reveal the first item with an exact node-name match."""
        target = node_name.strip()
        if not target:
            return False
        iterator = QTreeWidgetItemIterator(self._tree)
        while iterator.value() is not None:
            item = iterator.value()
            if item is not None and item.text(0) == target:
                self._tree.setCurrentItem(item)
                self._tree.scrollToItem(item)
                return True
            iterator += 1
        return False

    def _build_item(
        self,
        node: CallNode,
        *,
        total_ms: float,
        is_root: bool = False,
    ) -> QTreeWidgetItem:
        if not is_root and not self._filter.matches_subtree(node):
            return None  # type: ignore[return-value]
        pct = (node.total_ms_value / max(total_ms, 1e-6)) * 100.0
        item = QTreeWidgetItem(
            [
                node.name,
                f"{float(node.self_ms):.3f}",
                f"{node.total_ms_value:.3f}",
                f"{pct:.1f}",
                str(node.call_count),
                node.device.value.upper(),
            ]
        )
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        item.setTextAlignment(4, Qt.AlignmentFlag.AlignRight |
                              Qt.AlignmentFlag.AlignVCenter)
        for column in range(6):
            item.setForeground(column, _COLOR_TEXT)

        if is_root:
            font = item.font(0)
            font.setBold(True)
            for column in range(6):
                item.setFont(column, font)
                item.setBackground(column, _COLOR_ROOT)
        else:
            background = None
            ratio = node.total_ms_value / max(self._budget_ms, 1e-6)
            if ratio >= 1.0:
                background = _COLOR_SLOW
            elif ratio >= 0.8:
                background = _COLOR_WARN
            if background is not None:
                for column in range(6):
                    item.setBackground(column, background)

        for child in node.children:
            child_item = self._build_item(child, total_ms=total_ms)
            if child_item is not None:
                item.addChild(child_item)
        return item


__all__ = ["QProfileHierarchyWidget"]
