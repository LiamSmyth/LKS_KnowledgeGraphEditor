"""Custom time spinbox widget for PySide6.

Provides a spinbox that displays time in HH:MM format and increments/decrements
by a configurable number of minutes.
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


from PySide6.QtWidgets import QSpinBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator

class QTimeSpinBox(QSpinBox):
    """Spinbox for time entry in HH:MM format.

    Features:
    - Displays time as HH:MM (e.g., "02:30")
    - Increment/decrement by configurable minutes (default: 30)
    - Wraps around at 24 hours
    - Supports 12-hour AM/PM or 24-hour format

    The value is stored internally as total minutes since midnight (0-1439).
    """

    def __init__(
        self,
        use_ampm: bool = False,
        increment_minutes: int = 30,
        parent=None
    ):
        """Initialize time spinbox.

        Args:
            use_ampm: If True, display 12-hour AM/PM format; if False, 24-hour
            increment_minutes: Minutes to add/subtract on arrow clicks
            parent: Parent widget
        """
        super().__init__(parent)

        self._use_ampm = use_ampm
        self._increment_minutes = increment_minutes

        # Value is total minutes since midnight (0-1439)
        self.setRange(0, 1439)  # 24 * 60 - 1
        self.setValue(120)  # Default to 02:00
        self.setSingleStep(increment_minutes)
        self.setWrapping(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def textFromValue(self, minutes: int) -> str:
        """Convert minutes since midnight to display string.

        Args:
            minutes: Total minutes since midnight (0-1439)

        Returns:
            Formatted time string (e.g., "02:30" or "2:30 AM")
        """
        hours = minutes // 60
        mins = minutes % 60

        if self._use_ampm:
            ampm = "AM"
            display_hour = hours

            if hours == 0:
                display_hour = 12
            elif hours >= 12:
                ampm = "PM"
                if hours > 12:
                    display_hour = hours - 12

            return f"{display_hour}:{mins:02d} {ampm}"
        else:
            return f"{hours:02d}:{mins:02d}"

    def valueFromText(self, text: str) -> int:
        """Convert display string to minutes since midnight.

        Args:
            text: Time string (e.g., "02:30" or "2:30 AM")

        Returns:
            Total minutes since midnight (0-1439)
        """
        text = text.strip().upper()

        # Check for AM/PM
        ampm = None
        if text.endswith(" AM") or text.endswith(" PM"):
            ampm = text[-2:]
            text = text[:-3].strip()

        # Parse HH:MM
        try:
            if ":" in text:
                parts = text.split(":")
                hours = int(parts[0])
                mins = int(parts[1])

                # Convert 12-hour to 24-hour if needed
                if ampm:
                    if ampm == "PM" and hours != 12:
                        hours += 12
                    elif ampm == "AM" and hours == 12:
                        hours = 0

                # Clamp to valid range
                hours = max(0, min(23, hours))
                mins = max(0, min(59, mins))

                return hours * 60 + mins
        except (ValueError, IndexError):
            pass

        # Return current value if parsing fails
        return self.value()

    def validate(self, text: str, pos: int):
        """Validate input text.

        Args:
            text: Current text
            pos: Cursor position

        Returns:
            Validation state
        """
        # Allow intermediate states during typing
        return QValidator.State.Acceptable, text, pos

    def set_time(self, hours: int, minutes: int):
        """Set time from hour and minute components.

        Args:
            hours: Hour (0-23)
            minutes: Minutes (0-59)
        """
        total_minutes = hours * 60 + minutes
        self.setValue(total_minutes)

    def get_time(self) -> tuple[int, int]:
        """Get time as hour and minute components.

        Returns:
            Tuple of (hours, minutes) in 24-hour format
        """
        total_minutes = self.value()
        hours = total_minutes // 60
        minutes = total_minutes % 60
        return hours, minutes

    def get_time_string(self) -> str:
        """Get time as HH:MM string in 24-hour format.

        Returns:
            Time string (e.g., "02:30")
        """
        hours, minutes = self.get_time()
        return f"{hours:02d}:{minutes:02d}"
