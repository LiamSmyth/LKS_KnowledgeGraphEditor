"""ActivityLog widget - A scrollable activity log with timestamped, colored messages.

Messages are appended with timestamps and color-coded by level.
Supports info, warn, error, debug, and success levels.
"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

# Log level colors (Qt color names or hex)
LOG_COLORS: dict[str, str] = {
    "info": "#81c784",  # Green
    "warn": "#ffb74d",  # Orange
    "error": "#ef5350",  # Red
    "debug": "#90caf9",  # Blue
    "success": "#4caf50",  # Bright green
}

# Log level prefixes
LOG_PREFIXES: dict[str, str] = {
    "info": "",
    "warn": "⚠ ",
    "error": "✗ ",
    "debug": "[debug] ",
    "success": "✓ ",
}

# Default text edit styling
DEFAULT_LOG_STYLE: str = """
    QTextEdit {
        background: #1e1e1e;
        color: #d4d4d4;
        border: 1px solid #333;
        border-radius: 3px;
        font-family: Consolas, monospace;
        font-size: 9pt;
        padding: 4px;
    }
"""


class QActivityLog(QWidget):
    """A scrollable activity log with timestamped, colored messages.

    Messages are appended with timestamps and color-coded by level.
    Supports info, warn, error, debug, and success levels.

    Args:
        parent: Parent widget
        max_lines: Maximum number of lines to keep (0 = unlimited)
        show_timestamps: Whether to show timestamps
        min_height: Minimum height of the log widget
        max_height: Maximum height of the log widget

    Example:
        log = QActivityLog(parent)
        log.log_info("Operation started")
        log.log_success("Operation complete")
        log.log_error("Something failed")
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        max_lines: int = 200,
        show_timestamps: bool = True,
        min_height: int = 100,
        max_height: int = 150,
    ) -> None:
        """Initialize activity log.

        Args:
            parent: Parent widget
            max_lines: Max lines to keep
            show_timestamps: Whether to show timestamps
            min_height: Minimum height
            max_height: Maximum height
        """
        super().__init__(parent)
        self._max_lines = max_lines
        self._show_timestamps = show_timestamps

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setMinimumHeight(min_height)
        self._text_edit.setMaximumHeight(max_height)
        self._text_edit.setStyleSheet(DEFAULT_LOG_STYLE)
        layout.addWidget(self._text_edit)

    def _format_timestamp(self) -> str:
        """Format current timestamp.

        Returns:
            Formatted timestamp string
        """
        return datetime.now().strftime("%H:%M:%S")

    def _append_line(self, text: str, level: str) -> None:
        """Append a line to the log with color.

        Args:
            text: Message text
            level: Log level for color
        """
        # Build message with timestamp
        if self._show_timestamps:
            timestamp = self._format_timestamp()
            message = f"[{timestamp}] {LOG_PREFIXES.get(level, '')}{text}"
        else:
            message = f"{LOG_PREFIXES.get(level, '')}{text}"

        # Get color for level
        color = LOG_COLORS.get(level, "#d4d4d4")

        # Append with color
        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(
            f'<span style="color: {color};">{message}</span><br>')

        # Trim if exceeds max lines
        if self._max_lines > 0:
            text = self._text_edit.toPlainText()
            lines = text.split("\n")
            if len(lines) > self._max_lines:
                # Keep only last max_lines
                self._text_edit.setPlainText(
                    "\n".join(lines[-self._max_lines:]))

        # Auto-scroll to bottom
        self._text_edit.moveCursor(QTextCursor.End)

    def log_info(self, message: str) -> None:
        """Log an info message."""
        self._append_line(message, "info")

    def log_warn(self, message: str) -> None:
        """Log a warning message."""
        self._append_line(message, "warn")

    def log_error(self, message: str) -> None:
        """Log an error message."""
        self._append_line(message, "error")

    def log_debug(self, message: str) -> None:
        """Log a debug message."""
        self._append_line(message, "debug")

    def log_success(self, message: str) -> None:
        """Log a success message."""
        self._append_line(message, "success")

    def log(self, message: str, level: str = "info") -> None:
        """Log a message with specific level.

        Args:
            message: Message text
            level: Log level (info, warn, error, debug, success)
        """
        self._append_line(message, level)

    def clear(self) -> None:
        """Clear all log messages."""
        self._text_edit.clear()

    def get_text(self) -> str:
        """Get plain text content.

        Returns:
            Plain text log content
        """
        return self._text_edit.toPlainText()

    def get_html(self) -> str:
        """Get HTML content.

        Returns:
            HTML log content
        """
        return self._text_edit.toHtml()

    def set_max_lines(self, max_lines: int) -> None:
        """Set maximum number of lines.

        Args:
            max_lines: Max lines to keep
        """
        self._max_lines = max_lines

    def set_show_timestamps(self, show: bool) -> None:
        """Set whether to show timestamps.

        Args:
            show: Whether to show timestamps
        """
        self._show_timestamps = show

    def get_log_callback(self) -> Callable[[str], None]:
        """Get a callback function for logging info messages.

        Returns:
            Callable that logs info messages

        Example:
            callback = log.get_log_callback()
            callback("Some message")
        """
        return self.log_info
