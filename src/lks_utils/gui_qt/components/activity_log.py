"""
Activity log component with timestamped, color-coded entries.

Provides a timestamped activity log with color coding for different log levels
(info, success, warning, error, etc.).
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


from datetime import datetime
from typing import Any

from PySide6 import QtCore
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class QActivityLogComponent(QWidget):
    """
    Activity log component with timestamped, color-coded entries.

    Provides `.log(level, message)` API with automatic timestamps and color tags.
    Typical use: execution logs, progress updates, status messages.

    **Interface:**
    - `log(level, message)` → None
    - `info(message)` → None
    - `success(message)` → None
    - `warning(message)` → None
    - `error(message)` → None
    - `stage(message)` → None (light gray for stage markers)
    - `clear()` → None
    - `get_text()` → str
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None

    **Signals:**
    - `log_cleared` - Emitted when log is cleared

    **Example:**
    ```python
    log = QActivityLogComponent()
    layout.addWidget(log)

    log.info("Starting batch...")
    log.success("Job 1 complete")
    log.warning("Job 2 skipped")
    log.error("Job 3 failed: Connection timeout")
    log.stage("=== Phase 2: Compression ===")
    ```
    """

    log_cleared = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        show_clear_button: bool = True,
        timestamp_format: str = "%H:%M:%S",
    ):
        """
        Initialize activity log component.

        Args:
            parent: Parent widget.
            show_clear_button: Whether to show the Clear button.
            timestamp_format: Timestamp format (strftime format).
        """
        super().__init__(parent)

        self._show_clear = show_clear_button
        self._timestamp_format = timestamp_format

        # Define color formats for each log level
        self._formats: dict[str, QTextCharFormat] = {}
        self._setup_formats()

        self._setup_ui()

    def _setup_formats(self) -> None:
        """Set up text formats for each log level."""
        colors = {
            "timestamp": "#6c757d",
            "info": "#17a2b8",
            "success": "#28a745",
            "warning": "#ffc107",
            "error": "#dc3545",
            "stage": "#6c757d",
        }

        for level, color_hex in colors.items():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color_hex))
            self._formats[level] = fmt

    def _setup_ui(self) -> None:
        """Set up the activity log UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Log text widget
        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setTextInteractionFlags(
            self._log_text.textInteractionFlags() | 
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse |
            QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._log_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # Set monospace font
        font = self._log_text.font()
        font.setFamily("Consolas, Monaco, Courier New, monospace")
        font.setPointSize(9)
        self._log_text.setFont(font)

        # Set styling (darker background for logs)
        self._log_text.setStyleSheet(
            """
            QTextEdit {
                background-color: #1a1a1a;
                color: #ffffff;
                border: 1px solid #444444;
                padding: 5px;
            }
            """
        )

        layout.addWidget(self._log_text)

        # Clear button
        if self._show_clear:
            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(0, 0, 0, 0)

            self._clear_btn = QPushButton("🗑️ Clear Log")
            self._clear_btn.clicked.connect(self._on_clear_clicked)
            self._clear_btn.setToolTip("Clear all log entries")
            self._clear_btn.setMaximumWidth(120)
            button_layout.addStretch()
            button_layout.addWidget(self._clear_btn)

            layout.addLayout(button_layout)

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        self.clear()

    def log(self, level: str, message: str) -> None:
        """
        Log a message with specified level.

        Args:
            level: Log level ("info", "success", "warning", "error", "stage", or "timestamp").
            message: Message to log.
        """
        # Get current cursor at end
        cursor = self._log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Insert timestamp
        timestamp = datetime.now().strftime(self._timestamp_format)
        timestamp_fmt = self._formats.get("timestamp", QTextCharFormat())
        cursor.insertText(f"[{timestamp}] ", timestamp_fmt)

        # Insert message with level color
        message_fmt = self._formats.get(level, QTextCharFormat())
        cursor.insertText(f"{message}\n", message_fmt)

        # Auto-scroll to bottom
        self._log_text.ensureCursorVisible()

    def info(self, message: str) -> None:
        """Log an info message (cyan)."""
        self.log("info", message)

    def success(self, message: str) -> None:
        """Log a success message (green)."""
        self.log("success", message)

    def warning(self, message: str) -> None:
        """Log a warning message (yellow)."""
        self.log("warning", message)

    def error(self, message: str) -> None:
        """Log an error message (red)."""
        self.log("error", message)

    def stage(self, message: str) -> None:
        """Log a stage marker (gray)."""
        self.log("stage", message)

    def clear(self) -> None:
        """Clear all log entries."""
        self._log_text.clear()
        self.log_cleared.emit()

    def get_text(self) -> str:
        """
        Get the current log text.

        Returns:
            Current log text (plain text, without formatting).
        """
        return self._log_text.toPlainText()

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with current log text.
        """
        return {"text": self.get_text()}

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with log text. Note: formatting will be lost.
        """
        text = data.get("text", "")
        self._log_text.setPlainText(text)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: True to enable, False to disable.
        """
        self._log_text.setEnabled(enabled)
        if self._show_clear:
            self._clear_btn.setEnabled(enabled)
