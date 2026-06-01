"""Floating performance window for the knowledge graph canvas."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.widgets.frame_profiler_widget import QFrameProfilerWidget


class QKnowledgeGraphPerfWindow(QWidget):
    """Floating window that shows live frame timings for the graph canvas."""

    def __init__(self, canvas: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setObjectName("knowledge_graph_perf_window")
        self.setWindowTitle("Graph Performance")
        self.resize(920, 720)

        self._profiler = QFrameProfilerWidget(self)
        self._profiler.attach(canvas)
        self._profiler.set_processing_enabled(False)
        self._profiler.set_capture_enabled(False)

        self._warning_label = QLabel("No profiler warnings yet.", self)
        self._warning_label.setObjectName("graph_perf_warning_label")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #d0d0d0; padding: 4px 0;")
        self._profiler.profiler_warning.connect(self._warning_label.setText)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self._warning_label)
        layout.addWidget(self._profiler, stretch=1)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._profiler.set_processing_enabled(True)
        self._profiler.set_capture_enabled(True)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        self._profiler.set_capture_enabled(False)
        self._profiler.set_processing_enabled(False)
        super().hideEvent(event)


__all__ = ["QKnowledgeGraphPerfWindow"]
