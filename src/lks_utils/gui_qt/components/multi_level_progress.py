"""
Multi-level progress tracker component.

Provides a stack of progress bars with labels for hierarchical progress tracking
(e.g., batch → job → stage, or video → extraction → frame).
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


from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QProgressBar,
    QWidget,
)


@dataclass
class ProgressLevel:
    """Configuration for a single progress level."""

    name: str
    """Display name for this level (e.g., 'Batch', 'Job', 'Stage')."""

    color: str = "#17a2b8"
    """Progress bar color (QSS color string)."""

    label_width: int = 20
    """Width of the status label in characters."""

    tooltip: str = ""
    """Tooltip text for the level label."""


class QMultiLevelProgressComponent(QWidget):
    """
    Multi-level progress tracker with configurable levels.

    Displays N progress bars stacked vertically, each with a label and status text.
    Typical use: batch → job → stage, or pipeline → task → subtask.

    **Interface:**
    - `get_level_count()` → int
    - `set_progress(level, value, max_value, status)` → None
    - `reset()` → None
    - `reset_level(level)` → None
    - `get_progress(level)` → tuple[int, int, str]
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None

    **Signals:**
    - `progress_changed(level, value, max_value)` - Emitted when progress updates

    **Example:**
    ```python
    levels = [
        ProgressLevel("Batch", "#28a745", 15, "Overall batch progress"),
        ProgressLevel("Job", "#17a2b8", 25, "Current job"),
        ProgressLevel("Stage", "#ffc107", 35, "File-level progress"),
    ]
    progress = QMultiLevelProgressComponent(levels=levels)
    layout.addWidget(progress)

    # Update levels
    progress.set_progress(0, 3, 10, "Job 3 of 10")
    progress.set_progress(1, 50, 100, "Archiving files...")
    progress.set_progress(2, 1024*1024, 5*1024*1024, "2.5 MB / 5 MB")
    ```
    """

    progress_changed = Signal(int, int, int)  # level, value, max_value

    def __init__(
        self,
        parent: QWidget | None = None,
        levels: list[ProgressLevel] | None = None,
    ):
        """
        Initialize multi-level progress component.

        Args:
            parent: Parent widget.
            levels: List of progress level configurations. If None, creates
                    a default 2-level setup (Overall, Current).
        """
        super().__init__(parent)

        self._levels: list[ProgressLevel] = levels or [
            ProgressLevel("Overall", "#28a745", 15, "Overall progress"),
            ProgressLevel("Current", "#17a2b8", 25, "Current task"),
        ]

        self._progress_bars: list[QProgressBar] = []
        self._status_labels: list[QLabel] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the multi-level progress UI."""
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.setColumnStretch(1, 1)

        for row, level in enumerate(self._levels):
            # Level name label
            name_label = QLabel(f"{level.name}:")
            if level.tooltip:
                name_label.setToolTip(level.tooltip)
            layout.addWidget(name_label, row, 0)

            # Progress bar + status label container
            progress_bar = QProgressBar()
            progress_bar.setMinimum(0)
            progress_bar.setMaximum(100)
            progress_bar.setValue(0)
            progress_bar.setTextVisible(True)
            progress_bar.setFormat("%v/%m")

            # Apply color styling
            progress_bar.setStyleSheet(
                f"""
                QProgressBar {{
                    border: 1px solid #444;
                    border-radius: 3px;
                    text-align: center;
                    background-color: #2d2d2d;
                }}
                QProgressBar::chunk {{
                    background-color: {level.color};
                    border-radius: 2px;
                }}
                """
            )

            layout.addWidget(progress_bar, row, 1)

            # Status label
            status_label = QLabel("")
            status_label.setMinimumWidth(
                level.label_width * 8)  # ~8px per char
            layout.addWidget(status_label, row, 2)

            self._progress_bars.append(progress_bar)
            self._status_labels.append(status_label)

    def get_level_count(self) -> int:
        """Get the number of progress levels."""
        return len(self._levels)

    def set_progress(
        self, level: int, value: int, max_value: int, status: str = ""
    ) -> None:
        """
        Update progress for a specific level.

        Args:
            level: Level index (0-based).
            value: Current progress value.
            max_value: Maximum progress value.
            status: Status text to display next to progress bar.
        """
        if level < 0 or level >= len(self._progress_bars):
            return

        bar = self._progress_bars[level]
        bar.setMaximum(max_value)
        bar.setValue(value)

        if status:
            self._status_labels[level].setText(status)

        self.progress_changed.emit(level, value, max_value)

    def reset(self) -> None:
        """Reset all progress levels to 0."""
        for i in range(len(self._progress_bars)):
            self.reset_level(i)

    def reset_level(self, level: int) -> None:
        """
        Reset a specific progress level to 0.

        Args:
            level: Level index (0-based).
        """
        if level < 0 or level >= len(self._progress_bars):
            return

        self._progress_bars[level].setValue(0)
        self._progress_bars[level].setMaximum(100)
        self._status_labels[level].setText("")

    def get_progress(self, level: int) -> tuple[int, int, str]:
        """
        Get current progress for a level.

        Args:
            level: Level index (0-based).

        Returns:
            Tuple of (value, max_value, status_text).
        """
        if level < 0 or level >= len(self._progress_bars):
            return (0, 100, "")

        bar = self._progress_bars[level]
        return (bar.value(), bar.maximum(), self._status_labels[level].text())

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with progress state for all levels.
        """
        return {
            "levels": [
                {
                    "value": bar.value(),
                    "max_value": bar.maximum(),
                    "status": label.text(),
                }
                for bar, label in zip(self._progress_bars, self._status_labels)
            ]
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with progress state.
        """
        levels = data.get("levels", [])
        for i, level_data in enumerate(levels):
            if i >= len(self._progress_bars):
                break

            self.set_progress(
                i,
                level_data.get("value", 0),
                level_data.get("max_value", 100),
                level_data.get("status", ""),
            )

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all progress bars.

        Args:
            enabled: True to enable, False to disable.
        """
        for bar in self._progress_bars:
            bar.setEnabled(enabled)
        for label in self._status_labels:
            label.setEnabled(enabled)
