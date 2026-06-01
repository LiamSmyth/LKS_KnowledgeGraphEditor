"""Action timing table widgets for profiler UI."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.profiling.action_timing_profiler import ActionTimingEvent, ActionTimingStats


_COLOR_TEXT = QColor(0xCC, 0xCC, 0xCC)
_COLOR_OK_BG = QColor(0x2A, 0x56, 0x38, 72)
_COLOR_WARN_BG = QColor(0x6B, 0x5A, 0x22, 72)
_COLOR_FAIL_BG = QColor(0x7A, 0x33, 0x33, 88)


class QProfileActionsWidget(QWidget):
    """Displays aggregate and recent action-timing records."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stats: list[ActionTimingStats] = []
        self._events: list[ActionTimingEvent] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._summary_label = QLabel("No action timing samples yet.", self)
        self._summary_label.setFont(QFont("Consolas", 8))
        self._summary_label.setStyleSheet("color: #aaaaaa;")
        layout.addWidget(self._summary_label)

        self._stats_table = QTableWidget(0, 8, self)
        self._stats_table.setHorizontalHeaderLabels(
            ["Action", "Phase", "Count", "p50", "p95", "p99", "Mean", "Max"]
        )
        self._stats_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._stats_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._stats_table.setAlternatingRowColors(False)
        self._stats_table.setShowGrid(False)
        self._stats_table.verticalHeader().setVisible(False)
        self._stats_table.setFont(QFont("Consolas", 9))

        stats_header = self._stats_table.horizontalHeader()
        stats_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        stats_header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents)
        stats_header.setSectionResizeMode(
            7, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._stats_table)

        self._events_table = QTableWidget(0, 6, self)
        self._events_table.setHorizontalHeaderLabels(
            ["Time", "Action", "Phase", "Duration", "Outcome", "Metadata"]
        )
        self._events_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._events_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._events_table.setAlternatingRowColors(False)
        self._events_table.setShowGrid(False)
        self._events_table.verticalHeader().setVisible(False)
        self._events_table.setFont(QFont("Consolas", 9))

        events_header = self._events_table.horizontalHeader()
        events_header.setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        events_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        events_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        events_header.setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        events_header.setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)
        events_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._events_table)

    def set_data(
        self,
        *,
        stats: list[ActionTimingStats],
        events: list[ActionTimingEvent],
    ) -> None:
        self._stats = list(stats)
        self._events = list(events)
        self._populate_summary()
        self._populate_stats_table()
        self._populate_events_table()

    def clear(self) -> None:
        self._stats.clear()
        self._events.clear()
        self._summary_label.setText("No action timing samples yet.")
        self._stats_table.setRowCount(0)
        self._events_table.setRowCount(0)

    def _populate_summary(self) -> None:
        total_events = len(self._events)
        unique_actions = len({(row.action_id, row.phase)
                             for row in self._stats})
        if total_events == 0:
            self._summary_label.setText("No action timing samples yet.")
            return
        slowest = self._stats[0] if self._stats else None
        if slowest is None:
            self._summary_label.setText(
                f"events={total_events} | unique actions={unique_actions}"
            )
            return
        self._summary_label.setText(
            f"events={total_events} | unique actions={unique_actions} | "
            f"slowest p95={slowest.action_id}:{slowest.phase} ({slowest.p95_ms:.3f} ms)"
        )

    def _populate_stats_table(self) -> None:
        self._stats_table.setRowCount(len(self._stats))
        for row_idx, row in enumerate(self._stats):
            row_items = [
                QTableWidgetItem(row.action_id),
                QTableWidgetItem(row.phase),
                QTableWidgetItem(str(row.count)),
                QTableWidgetItem(f"{row.p50_ms:.3f}"),
                QTableWidgetItem(f"{row.p95_ms:.3f}"),
                QTableWidgetItem(f"{row.p99_ms:.3f}"),
                QTableWidgetItem(f"{row.mean_ms:.3f}"),
                QTableWidgetItem(f"{row.max_ms:.3f}"),
            ]
            bg = self._stats_row_background(row)
            for col_idx, item in enumerate(row_items):
                item.setForeground(_COLOR_TEXT)
                if bg is not None:
                    item.setBackground(bg)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (Qt.AlignmentFlag.AlignRight if col_idx >= 2 else Qt.AlignmentFlag.AlignLeft)
                )
                self._stats_table.setItem(row_idx, col_idx, item)

    def _populate_events_table(self) -> None:
        recent = list(reversed(self._events[-80:]))
        self._events_table.setRowCount(len(recent))
        for row_idx, event in enumerate(recent):
            dt = datetime.fromtimestamp(event.ended_at_s)
            metadata_text = self._metadata_text(event.metadata)
            row_items = [
                QTableWidgetItem(dt.strftime("%H:%M:%S.%f")[:-3]),
                QTableWidgetItem(event.action_id),
                QTableWidgetItem(event.phase),
                QTableWidgetItem(f"{event.duration_ms:.3f}"),
                QTableWidgetItem(event.outcome),
                QTableWidgetItem(metadata_text),
            ]
            bg = self._event_row_background(event)
            for col_idx, item in enumerate(row_items):
                item.setForeground(_COLOR_TEXT)
                if bg is not None:
                    item.setBackground(bg)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (Qt.AlignmentFlag.AlignRight if col_idx == 3 else Qt.AlignmentFlag.AlignLeft)
                )
                self._events_table.setItem(row_idx, col_idx, item)

    @staticmethod
    def _metadata_text(metadata: dict[str, object]) -> str:
        if not metadata:
            return ""
        parts: list[str] = []
        for key in sorted(metadata):
            value = metadata[key]
            parts.append(f"{key}={value}")
        return ", ".join(parts)

    @staticmethod
    def _event_row_background(event: ActionTimingEvent) -> QColor | None:
        outcome = event.outcome.strip().lower()
        if outcome in {"error", "fail", "failed"}:
            return _COLOR_FAIL_BG
        if outcome in {"warn", "warning"}:
            return _COLOR_WARN_BG
        return _COLOR_OK_BG

    @staticmethod
    def _stats_row_background(row: ActionTimingStats) -> QColor | None:
        if row.p95_ms > 100.0:
            return _COLOR_FAIL_BG
        if row.p95_ms > 33.0:
            return _COLOR_WARN_BG
        return _COLOR_OK_BG


__all__ = ["QProfileActionsWidget"]
