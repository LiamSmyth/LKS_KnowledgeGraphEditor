"""QColoredLogWidget - Color-coded log display widget for PySide6.

A read-only text display widget with support for color-coded log levels:
- ERROR: Red text
- WARNING: Yellow/Orange text
- SUCCESS: Green text
- INFO: Cyan/Blue text
- DEFAULT: White/Default text

Pattern ported from multiple tkinter GUIs using ScrolledText with tag_config.
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


from PySide6.QtWidgets import QTextEdit, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor, QColor


class QColoredLogWidget(QTextEdit):
    """Read-only text widget with color-coded log levels.

    Usage:
        log = QColoredLogWidget()
        log.log("error", "Something went wrong")
        log.log("success", "Operation completed")
        log.log("info", "Processing file...")
        log.clear_log()

    Features:
        - Color-coded text based on log level
        - Read-only to prevent user editing
        - Auto-scroll to bottom on new entries
        - Clear log functionality
    """

    # Color definitions (matching common GUI patterns)
    COLORS = {
        "error": "#dc3545",      # Red
        "warning": "#ffc107",    # Yellow/Orange
        "success": "#28a745",    # Green
        "info": "#17a2b8",       # Cyan
        "header": "#6c757d",     # Gray (for headers/separators)
        "default": "#ffffff",    # White (default text)
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the colored log widget.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)

        # Configure as read-only
        self.setReadOnly(True)

        # Set monospace font for better log readability
        font = self.font()
        font.setFamily("Consolas, Monaco, Courier New, monospace")
        font.setPointSize(9)
        self.setFont(font)

        # Set dark background for better contrast
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 1px solid #444444;
            }
        """)

        # Pre-create text formats for each log level
        self._formats: dict[str, QTextCharFormat] = {}
        for level, color_hex in self.COLORS.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color_hex))
            if level == "header":
                font_header = self.font()
                font_header.setBold(True)
                fmt.setFont(font_header)
            self._formats[level] = fmt

    def log(self, level: str, message: str) -> None:
        """Append a log message with color coding.

        Args:
            level: Log level (error, warning, success, info, header, default)
            message: Message text to append
        """
        # Normalize level to lowercase
        level = level.lower()

        # Get the appropriate format (default if level not recognized)
        fmt = self._formats.get(level, self._formats["default"])

        # Move cursor to end
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Insert formatted text
        cursor.insertText(message + "\n", fmt)

        # Auto-scroll to bottom
        self.ensureCursorVisible()

    def clear_log(self) -> None:
        """Clear all log content."""
        self.clear()

    def append_plain(self, text: str) -> None:
        """Append plain text without color coding.

        Args:
            text: Plain text to append
        """
        self.log("default", text)
