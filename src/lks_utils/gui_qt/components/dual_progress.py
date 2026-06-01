"""Dual progress bar component (PySide6).

A reusable UI component for showing two-level progress:
- Overall/global progress (e.g., "Processing 5 of 10 files")
- Current task progress (e.g., "Compressing: 75%")

Example:
    from lks_utils.gui_qt.components import QDualProgressComponent
    
    progress = QDualProgressComponent(
        parent,
        title="Progress",
        show_percentage=True,
    )
    
    # Update progress
    progress.set_overall(50, "Processing 5 of 10 files...")
    progress.set_task(75, "Compressing image.jpg...")
    
    # Reset
    progress.reset()
    
    # State persistence (typically not needed for progress, but available)
    state = progress.to_dict()
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QWidget,
)


class QDualProgressComponent(QWidget):
    """Dual progress bars for overall and task-level progress.

    Provides a consistent UI pattern for showing hierarchical progress.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "Progress",
        overall_label: str = "Overall:",
        task_label: str = "Current:",
        show_percentage: bool = True,
        show_eta: bool = False,
    ) -> None:
        """Initialize the dual progress component.

        Args:
            parent: Parent widget
            title: Title for the group box (empty to use plain frame)
            overall_label: Label for overall progress bar
            task_label: Label for task progress bar
            show_percentage: Whether to show percentage labels
            show_eta: Whether to show ETA (placeholder, not implemented)
        """
        super().__init__(parent)

        self.show_percentage: bool = show_percentage
        self.show_eta: bool = show_eta
        self.title: str = title

        # State
        self._overall_progress: float = 0
        self._task_progress: float = 0
        self._overall_status: str = ""
        self._task_status: str = ""

        self._build_ui(overall_label, task_label)

    def _build_ui(self, overall_label: str, task_label: str) -> None:
        """Build the component UI."""
        # Create main container (group box if title provided)
        if self.title:
            container = QGroupBox(self.title)
        else:
            container = QFrame()

        # Layout for this widget
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container, 0, 0)

        # Layout for the container
        layout = QGridLayout(container)
        layout.setSpacing(5)
        layout.setColumnStretch(1, 1)

        row: int = 0

        # Overall progress row
        overall_lbl = QLabel(overall_label)
        layout.addWidget(overall_lbl, row, 0, Qt.AlignmentFlag.AlignLeft)

        # Overall progress bar container
        overall_bar_frame = QFrame()
        overall_bar_layout = QGridLayout(overall_bar_frame)
        overall_bar_layout.setContentsMargins(0, 0, 0, 0)
        overall_bar_layout.setSpacing(5)
        overall_bar_layout.setColumnStretch(0, 1)

        self._overall_bar = QProgressBar()
        self._overall_bar.setRange(0, 100)
        self._overall_bar.setValue(0)
        overall_bar_layout.addWidget(self._overall_bar, 0, 0)

        if self.show_percentage:
            self._overall_pct_label = QLabel("0%")
            self._overall_pct_label.setFixedWidth(40)
            self._overall_pct_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            overall_bar_layout.addWidget(self._overall_pct_label, 0, 1)

        layout.addWidget(overall_bar_frame, row, 1)

        row += 1

        # Overall status
        self._overall_status_label = QLabel("")
        self._overall_status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._overall_status_label, row, 0,
                         1, 2, Qt.AlignmentFlag.AlignLeft)

        row += 1

        # Task progress row
        task_lbl = QLabel(task_label)
        layout.addWidget(task_lbl, row, 0, Qt.AlignmentFlag.AlignLeft)

        # Task progress bar container
        task_bar_frame = QFrame()
        task_bar_layout = QGridLayout(task_bar_frame)
        task_bar_layout.setContentsMargins(0, 0, 0, 0)
        task_bar_layout.setSpacing(5)
        task_bar_layout.setColumnStretch(0, 1)

        self._task_bar = QProgressBar()
        self._task_bar.setRange(0, 100)
        self._task_bar.setValue(0)
        task_bar_layout.addWidget(self._task_bar, 0, 0)

        if self.show_percentage:
            self._task_pct_label = QLabel("0%")
            self._task_pct_label.setFixedWidth(40)
            self._task_pct_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            task_bar_layout.addWidget(self._task_pct_label, 0, 1)

        layout.addWidget(task_bar_frame, row, 1)

        row += 1

        # Task status
        self._task_status_label = QLabel("")
        self._task_status_label.setStyleSheet("color: gray;")
        layout.addWidget(self._task_status_label, row, 0,
                         1, 2, Qt.AlignmentFlag.AlignLeft)

    def set_overall(self, progress: float, status: str = "") -> None:
        """Set overall progress.

        Args:
            progress: Progress value (0-100)
            status: Status text to display
        """
        clamped: float = max(0, min(100, progress))
        self._overall_progress = clamped
        self._overall_bar.setValue(int(clamped))
        self._overall_status = status
        self._overall_status_label.setText(status)

        if self.show_percentage:
            self._overall_pct_label.setText(f"{int(clamped)}%")

    def set_task(self, progress: float, status: str = "") -> None:
        """Set task progress.

        Args:
            progress: Progress value (0-100)
            status: Status text to display
        """
        clamped: float = max(0, min(100, progress))
        self._task_progress = clamped
        self._task_bar.setValue(int(clamped))
        self._task_status = status
        self._task_status_label.setText(status)

        if self.show_percentage:
            self._task_pct_label.setText(f"{int(clamped)}%")

    def reset(self) -> None:
        """Reset both progress bars to 0."""
        self.set_overall(0, "")
        self.set_task(0, "")

    def set_indeterminate(self, overall: bool = False, task: bool = False) -> None:
        """Set progress bars to indeterminate mode.

        Args:
            overall: Set overall bar to indeterminate
            task: Set task bar to indeterminate
        """
        if overall:
            self._overall_bar.setRange(0, 0)  # Indeterminate mode in Qt
        else:
            self._overall_bar.setRange(0, 100)  # Determinate mode

        if task:
            self._task_bar.setRange(0, 0)  # Indeterminate mode in Qt
        else:
            self._task_bar.setRange(0, 100)  # Determinate mode

    @property
    def overall_progress(self) -> float:
        """Get current overall progress value."""
        return self._overall_progress

    @property
    def task_progress(self) -> float:
        """Get current task progress value."""
        return self._task_progress

    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dict for persistence.

        Note: Progress state is typically not persisted, but this
        is provided for consistency with other components.

        Returns:
            Dictionary with progress state
        """
        return {
            "overall_progress": self._overall_progress,
            "task_progress": self._task_progress,
            "overall_status": self._overall_status,
            "task_status": self._task_status,
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore component state from dict.

        Args:
            state: Dictionary with progress state
        """
        if "overall_progress" in state:
            self.set_overall(
                state["overall_progress"],
                state.get("overall_status", "")
            )
        if "task_progress" in state:
            self.set_task(
                state["task_progress"],
                state.get("task_status", "")
            )

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component (visual only).

        Args:
            enabled: True to enable, False to disable
        """
        color: str = "gray" if enabled else "darkgray"
        self._overall_status_label.setStyleSheet(f"color: {color};")
        self._task_status_label.setStyleSheet(f"color: {color};")
