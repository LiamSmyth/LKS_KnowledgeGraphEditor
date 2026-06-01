"""QResultsDisplay - Read-only text display widget for results and output.

A simple, read-only text display widget suitable for showing batch operation results,
file lists, logs, or any multiline text output. Similar to tkinter's ScrolledText
but with a consistent API for appending and clearing content.

Pattern ported from multiple GUIs using ScrolledText for results display.
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


class QResultsDisplay(QTextEdit):
    """Read-only text widget for displaying results and output.

    Usage:
        results = QResultsDisplay()
        results.append_text("Processing complete\\n")
        results.append_text("Found 42 items\\n")
        results.clear_display()

    Features:
        - Read-only to prevent user editing
        - Auto-scroll to bottom on new entries
        - Clear display functionality
        - Word wrapping enabled by default
        - Monospace font for better readability
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the results display widget.

        Args:
            parent: Parent widget (optional)
        """
        super().__init__(parent)

        # Configure as read-only
        self.setReadOnly(True)

        # Enable word wrapping
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # Set monospace font for better readability
        font = self.font()
        font.setFamily("Consolas, Monaco, Courier New, monospace")
        font.setPointSize(9)
        self.setFont(font)

        # Set styling (light background for results, not as dark as log)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #2a2a2a;
                color: #ffffff;
                border: 1px solid #444444;
                padding: 5px;
            }
        """)

    def append_text(self, text: str) -> None:
        """Append text to the display.

        Args:
            text: Text to append (newline NOT automatically added)
        """
        # Move cursor to end and insert text
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.insertPlainText(text)

        # Auto-scroll to bottom
        self.ensureCursorVisible()

    def append_line(self, text: str) -> None:
        """Append a line of text (with automatic newline).

        Args:
            text: Text line to append
        """
        self.append_text(text + "\n")

    def set_text(self, text: str) -> None:
        """Replace all content with new text.

        Args:
            text: New content to set
        """
        self.setPlainText(text)

    def get_text(self) -> str:
        """Get the current text content.

        Returns:
            Current text content
        """
        return self.toPlainText()

    def clear_display(self) -> None:
        """Clear all display content."""
        self.clear()
