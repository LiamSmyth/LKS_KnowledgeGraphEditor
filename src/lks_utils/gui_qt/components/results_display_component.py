"""
Results display component with action buttons.

Wraps QResultsDisplay widget in a component interface with Copy and Clear buttons.
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

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.widgets.results_display import QResultsDisplay


class QResultsDisplayComponent(QWidget):
    """
    Results display component with copy/clear buttons.

    Wraps QResultsDisplay widget with action buttons for common operations.
    Typical use: displaying batch operation results, file lists, processing output.

    **Interface:**
    - `append_text(text)` → None
    - `append_line(text)` → None
    - `set_text(text)` → None
    - `get_text()` → str
    - `clear()` → None
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None

    **Signals:**
    - `text_cleared` - Emitted when display is cleared

    **Example:**
    ```python
    results = QResultsDisplayComponent()
    layout.addWidget(results)

    # Append results
    results.append_line("Processing complete!")
    results.append_line(f"Found {count} items")

    # Copy to clipboard
    # (user clicks Copy button)

    # Clear display
    results.clear()
    ```
    """

    text_cleared = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        show_copy_button: bool = True,
        show_clear_button: bool = True,
    ):
        """
        Initialize results display component.

        Args:
            parent: Parent widget.
            show_copy_button: Whether to show the Copy button.
            show_clear_button: Whether to show the Clear button.
        """
        super().__init__(parent)

        self._show_copy = show_copy_button
        self._show_clear = show_clear_button

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the results display UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Results display widget
        self._display = QResultsDisplay()
        layout.addWidget(self._display)

        # Button bar
        if self._show_copy or self._show_clear:
            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(0, 0, 0, 0)

            if self._show_copy:
                self._copy_btn = QPushButton("📋 Copy to Clipboard")
                self._copy_btn.clicked.connect(self._on_copy_clicked)
                self._copy_btn.setToolTip("Copy all results to clipboard")
                button_layout.addWidget(self._copy_btn)

            if self._show_clear:
                self._clear_btn = QPushButton("🗑️ Clear")
                self._clear_btn.clicked.connect(self._on_clear_clicked)
                self._clear_btn.setToolTip("Clear all results")
                button_layout.addWidget(self._clear_btn)

            button_layout.addStretch()
            layout.addLayout(button_layout)

    def _on_copy_clicked(self) -> None:
        """Handle copy button click."""
        text = self._display.get_text()
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)

    def _on_clear_clicked(self) -> None:
        """Handle clear button click."""
        self._display.clear_display()
        self.text_cleared.emit()

    # Public API

    def append_text(self, text: str) -> None:
        """
        Append text to the display.

        Args:
            text: Text to append (newline NOT automatically added).
        """
        self._display.append_text(text)

    def append_line(self, text: str) -> None:
        """
        Append a line of text (with automatic newline).

        Args:
            text: Text line to append.
        """
        self._display.append_line(text)

    def set_text(self, text: str) -> None:
        """
        Replace all content with new text.

        Args:
            text: New content to set.
        """
        self._display.set_text(text)

    def get_text(self) -> str:
        """
        Get the current text content.

        Returns:
            Current text content.
        """
        return self._display.get_text()

    def clear(self) -> None:
        """Clear all display content."""
        self._display.clear_display()
        self.text_cleared.emit()

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with current text content.
        """
        return {"text": self.get_text()}

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with text content.
        """
        text = data.get("text", "")
        self.set_text(text)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: True to enable, False to disable.
        """
        self._display.setEnabled(enabled)
        if self._show_copy:
            self._copy_btn.setEnabled(enabled)
        if self._show_clear:
            self._clear_btn.setEnabled(enabled)
