"""Qt Schedule Config Component - Schedule configuration UI.

Provides UI for configuring scheduled task settings (manual/daily/weekly + time).
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

from PySide6.QtWidgets import (
    QWidget,
    QGridLayout,
    QLabel,
    QComboBox,
)
from PySide6.QtCore import Signal

from lks_utils.gui_qt.widgets.time_spinbox import QTimeSpinBox


class QScheduleConfigComponent(QWidget):
    """Schedule configuration component.

    Features:
    - Schedule type selector (manual/daily/weekly)
    - Time entry with spinboxes (12-hour AM/PM or 24-hour format)
    - Configurable time increment (default 30 minutes)
    - Change signal emitted on any change

    Signals:
        changed: Emitted when any schedule setting changes

    Example:
        # 24-hour format (default)
        schedule_config = QScheduleConfigComponent()

        # 12-hour AM/PM format with 15-minute increments
        schedule_config = QScheduleConfigComponent(
            use_ampm=True,
            time_increment_minutes=15
        )

        # Get settings (always returns 24-hour format)
        schedule_type, schedule_time = schedule_config.get_schedule()

        # Set settings (accepts both formats)
        schedule_config.set_schedule("daily", "02:00")
        schedule_config.set_schedule("daily", "2:00 AM")
    """

    # Signals
    changed = Signal()

    def __init__(
        self,
        label: str = "Schedule:",
        default_type: str = "manual",
        default_time: str = "02:00",
        use_ampm: bool = False,
        time_increment_minutes: int = 30,
        parent: QWidget | None = None
    ):
        """Initialize component.

        Args:
            label: Label text for the schedule type selector
            default_type: Default schedule type ("manual", "daily", "weekly")
            default_time: Default time in HH:MM format (24-hour)
            use_ampm: If True, use 12-hour AM/PM format; if False, use 24-hour format
            time_increment_minutes: Time increment for spinbox arrows (e.g., 30 for 30-minute steps)
            parent: Parent widget
        """
        super().__init__(parent)

        self._default_type = default_type
        self._default_time = default_time
        self._use_ampm = use_ampm
        self._time_increment = time_increment_minutes

        self._setup_ui(label)

        # Set defaults
        self.set_schedule(default_type, default_time)

    def _setup_ui(self, label: str):
        """Setup the UI layout."""
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)

        # Grid layout:
        # Column 0: Type label (fixed width)
        # Column 1: Type combo (fixed width)
        # Column 2: Time label (fixed width)
        # Column 3: Time spinbox (fixed width)

        row = 0

        # Schedule type label - fixed width for alignment
        type_label = QLabel(label)
        type_label.setFixedWidth(100)
        layout.addWidget(type_label, row, 0)

        # Schedule type combo
        self._type_combo = QComboBox()
        self._type_combo.addItems(["manual", "daily", "weekly"])
        self._type_combo.setFixedWidth(90)
        self._type_combo.currentTextChanged.connect(self._on_changed)
        layout.addWidget(self._type_combo, row, 1)

        # Time label - fixed width for alignment
        time_label = QLabel("Time:")
        time_label.setFixedWidth(40)
        layout.addWidget(time_label, row, 2)

        # Time spinbox
        self._time_spinbox = QTimeSpinBox(
            use_ampm=self._use_ampm,
            increment_minutes=self._time_increment
        )
        self._time_spinbox.setFixedWidth(90)
        self._time_spinbox.valueChanged.connect(self._on_changed)
        layout.addWidget(self._time_spinbox, row, 3)

        # Add stretch to push everything left
        layout.setColumnStretch(4, 1)

    def _on_changed(self):
        """Handle change in schedule settings."""
        self.changed.emit()

    def get_schedule(self) -> tuple[str, str]:
        """Get current schedule settings.

        Returns:
            Tuple of (schedule_type, schedule_time) where time is in 24-hour HH:MM format
        """
        schedule_type = self._type_combo.currentText()
        schedule_time = self._time_spinbox.get_time_string()
        return schedule_type, schedule_time

    def set_schedule(self, schedule_type: str, schedule_time: str):
        """Set schedule settings.

        Args:
            schedule_type: Schedule type ("manual", "daily", "weekly")
            schedule_time: Time in HH:MM format (24-hour) or "H:MM AM/PM" format
        """
        # Block signals during update
        self._type_combo.blockSignals(True)
        self._time_spinbox.blockSignals(True)

        # Set schedule type
        index = self._type_combo.findText(schedule_type)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)

        # Parse time (support both 24-hour and AM/PM format)
        hour, minute, _ = self._parse_time(schedule_time)
        self._time_spinbox.set_time(hour, minute)

        # Re-enable signals
        self._type_combo.blockSignals(False)
        self._time_spinbox.blockSignals(False)

    def _parse_time(self, time_str: str) -> tuple[int, int, str | None]:
        """Parse time string.

        Args:
            time_str: Time in "HH:MM" (24-hour) or "H:MM AM/PM" format

        Returns:
            Tuple of (hour, minute, ampm) where ampm is None for 24-hour format
        """
        time_str = time_str.strip()

        # Check for AM/PM
        ampm = None
        if time_str.upper().endswith(" AM") or time_str.upper().endswith(" PM"):
            ampm = time_str[-2:].upper()
            time_str = time_str[:-3].strip()

        # Split hour and minute
        if ":" in time_str:
            parts = time_str.split(":")
            try:
                hour = int(parts[0])
                minute = int(parts[1])
                return hour, minute, ampm
            except ValueError:
                pass

        # Default to 02:00
        return 2, 0, ampm

    def get_schedule_type(self) -> str:
        """Get schedule type.

        Returns:
            Schedule type ("manual", "daily", "weekly")
        """
        return self._type_combo.currentText()

    def set_schedule_type(self, schedule_type: str):
        """Set schedule type.

        Args:
            schedule_type: Schedule type ("manual", "daily", "weekly")
        """
        index = self._type_combo.findText(schedule_type)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)

    def get_schedule_time(self) -> str:
        """Get schedule time.

        Returns:
            Time in 24-hour HH:MM format
        """
        _, time = self.get_schedule()
        return time

    def set_schedule_time(self, schedule_time: str):
        """Set schedule time.

        Args:
            schedule_time: Time in HH:MM format (24-hour) or "H:MM AM/PM" format
        """
        schedule_type = self.get_schedule_type()
        self.set_schedule(schedule_type, schedule_time)

    def is_manual(self) -> bool:
        """Check if schedule is manual.

        Returns:
            True if schedule type is "manual"
        """
        return self.get_schedule_type() == "manual"

    def validate(self) -> tuple[bool, str]:
        """Validate schedule settings.

        Returns:
            Tuple of (valid, error_message)
        """
        # Time is always valid with spinboxes (constrained to valid ranges)
        return True, ""

    # State persistence
    def to_dict(self) -> dict[str, Any]:
        """Export state for persistence.

        Returns:
            State dictionary
        """
        schedule_type, schedule_time = self.get_schedule()
        return {
            "schedule_type": schedule_type,
            "schedule_time": schedule_time,
        }

    def from_dict(self, state: dict[str, Any]):
        """Restore state from dictionary.

        Args:
            state: State dictionary from to_dict()
        """
        schedule_type = state.get("schedule_type", self._default_type)
        schedule_time = state.get("schedule_time", self._default_time)
        self.set_schedule(schedule_type, schedule_time)
