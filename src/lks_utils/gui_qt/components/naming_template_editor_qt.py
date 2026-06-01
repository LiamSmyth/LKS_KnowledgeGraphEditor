"""
Qt component for editing naming templates.

Provides:
- Text input for template string
- Token insertion buttons
- Format helper dropdowns
- Live preview with example filename
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

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QComboBox,
    QSpinBox,
    QGroupBox,
    QGridLayout,
    QToolTip,
)
from PySide6.QtGui import QCursor

from lks_utils.text.naming_template import NamingTemplate


class QNamingTemplateEditor(QWidget):
    """
    Qt component for editing naming templates.

    Features:
    - Template input field
    - Token insertion buttons
    - Format helper for date/datetime/index
    - Live preview

    Signals:
        template_changed: Emitted when template changes
    """

    template_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._template_input: QLineEdit | None = None
        self._preview_label: QLabel | None = None
        self._date_format_combo: QComboBox | None = None
        self._time_format_combo: QComboBox | None = None
        self._index_padding_spin: QSpinBox | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Template input section
        input_group = QGroupBox("Template")
        input_layout = QVBoxLayout(input_group)

        self._template_input = QLineEdit()
        self._template_input.setPlaceholderText(
            "Enter template (e.g., {base_name}_{date})")
        self._template_input.textChanged.connect(self._on_template_changed)
        input_layout.addWidget(self._template_input)

        layout.addWidget(input_group)

        # Token insertion buttons - all in one line
        token_group = QGroupBox("Insert Tokens")
        token_layout = QHBoxLayout(token_group)

        tokens = [
            ("{base_name}", "Base filename",
             "Original filename without extension", None),
            (None, "Date", "Current date (uses format from dropdown)", "date"),
            (None, "Time", "Current time (uses format from dropdown)", "time"),
            ("{datetime}", "Date/Time", "Full datetime stamp", None),
            (None, "Index", "Sequential number (uses padding from spinbox)", "index"),
            ("{ext}", "Extension", "File extension without dot", None),
            ("{.ext}", "Extension w/ dot", "File extension with leading dot", None),
        ]

        for token, label, tooltip, special in tokens:
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            if special == "date":
                btn.clicked.connect(lambda checked: self._insert_date_token())
            elif special == "time":
                btn.clicked.connect(lambda checked: self._insert_time_token())
            elif special == "index":
                btn.clicked.connect(lambda checked: self._insert_index_token())
            else:
                btn.clicked.connect(
                    lambda checked, t=token: self._insert_token(t))
            token_layout.addWidget(btn)

        token_layout.addStretch()
        layout.addWidget(token_group)

        # Format helpers - compact
        format_group = QGroupBox("Format Helpers")
        format_layout = QHBoxLayout(format_group)

        # Date format dropdown
        format_layout.addWidget(QLabel("Date format:"))

        from PySide6.QtWidgets import QComboBox, QSpinBox

        self._date_format_combo = QComboBox()
        self._date_format_combo.addItem(
            "Default (2026-01-27)", "{date:%Y-%m-%d}")
        self._date_format_combo.addItem("Compact (20260127)", "{date:%Y%m%d}")
        self._date_format_combo.addItem(
            "Day first (27-01-2026)", "{date:%d-%m-%Y}")
        self._date_format_combo.addItem(
            "Month name (January 27)", "{date:%B %d}")
        self._date_format_combo.addItem(
            "Underscores (2026_01_27)", "{date:%Y_%m_%d}")
        format_layout.addWidget(self._date_format_combo)

        format_layout.addSpacing(20)

        # Time format dropdown
        format_layout.addWidget(QLabel("Time format:"))

        self._time_format_combo = QComboBox()
        self._time_format_combo.addItem(
            "Default (14-30-52)", "{time:%H-%M-%S}")
        self._time_format_combo.addItem("Compact (143052)", "{time:%H%M%S}")
        self._time_format_combo.addItem(
            "With colons (14:30:52)", "{time:%H:%M:%S}")
        self._time_format_combo.addItem(
            "Underscores (14_30_52)", "{time:%H_%M_%S}")
        self._time_format_combo.addItem(
            "Hour-Min (14-30)", "{time:%H-%M}")
        format_layout.addWidget(self._time_format_combo)

        format_layout.addSpacing(20)

        # Index padding spinbox
        format_layout.addWidget(QLabel("Index padding:"))

        self._index_padding_spin = QSpinBox()
        self._index_padding_spin.setMinimum(0)
        self._index_padding_spin.setMaximum(10)
        self._index_padding_spin.setValue(0)
        self._index_padding_spin.setToolTip(
            "Number of digits for index (0 = no padding)")
        format_layout.addWidget(self._index_padding_spin)

        format_layout.addStretch()
        layout.addWidget(format_group)

        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self._preview_label = QLabel("(Preview will appear here)")
        self._preview_label.setStyleSheet(
            "padding: 10px; background-color: #2b2b2b; border-radius: 4px;")
        self._preview_label.setWordWrap(True)
        preview_layout.addWidget(self._preview_label)

        layout.addWidget(preview_group)

        # Add help text
        help_text = QLabel(
            "💡 Tip: Click token buttons to insert at cursor position. "
            "Use format helpers for common patterns."
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet(
            "color: #888; font-style: italic; padding: 5px;")
        layout.addWidget(help_text)

    def _insert_date_token(self) -> None:
        """Insert date token with format from dropdown."""
        if self._date_format_combo is None:
            return
        date_token = self._date_format_combo.currentData()
        if date_token:
            self._insert_token(date_token)

    def _insert_time_token(self) -> None:
        """Insert time token with format from dropdown."""
        if self._time_format_combo is None:
            return
        time_token = self._time_format_combo.currentData()
        if time_token:
            self._insert_token(time_token)

    def _insert_index_token(self) -> None:
        """Insert index token with padding from spinbox."""
        if self._index_padding_spin is None:
            return
        padding = self._index_padding_spin.value()
        if padding == 0:
            token = "{index}"
        else:
            token = f"{{index:0{padding}d}}"
        self._insert_token(token)

    def _insert_token(self, token: str) -> None:
        """Insert token at cursor position."""
        if self._template_input is None:
            return

        cursor_pos = self._template_input.cursorPosition()
        current_text = self._template_input.text()

        new_text = current_text[:cursor_pos] + \
            token + current_text[cursor_pos:]
        self._template_input.setText(new_text)

        # Move cursor after inserted token
        self._template_input.setCursorPosition(cursor_pos + len(token))
        self._template_input.setFocus()

        # Update preview immediately
        self._update_preview(new_text)

    def _on_template_changed(self) -> None:
        """Handle template text change."""
        template_str = self.get_template()

        # Update preview
        self._update_preview(template_str)

        # Emit signal
        self.template_changed.emit(template_str)

    def _update_preview(self, template_str: str) -> None:
        """Update preview label with example output."""
        if self._preview_label is None:
            return

        if not template_str:
            self._preview_label.setText("(Empty template)")
            self._preview_label.setStyleSheet(
                "padding: 10px; background-color: #2b2b2b; border-radius: 4px; color: #888;")
            return

        try:
            template = NamingTemplate(template_str)

            # Validate
            is_valid, error_msg = template.validate()

            if not is_valid:
                self._preview_label.setText(f"❌ Invalid: {error_msg}")
                self._preview_label.setStyleSheet(
                    "padding: 10px; background-color: #3d1f1f; border-radius: 4px; color: #ff6b6b;")
                return

            # Get example render using the actual template
            example = NamingTemplate.get_example_render(template_str)

            self._preview_label.setText(f"✓ Example: {example}")
            self._preview_label.setStyleSheet(
                "padding: 10px; background-color: #1f3d1f; border-radius: 4px; color: #6bff6b;")

        except Exception as e:
            self._preview_label.setText(f"❌ Error: {str(e)}")
            self._preview_label.setStyleSheet(
                "padding: 10px; background-color: #3d1f1f; border-radius: 4px; color: #ff6b6b;")

    def get_template(self) -> str:
        """
        Get current template string.

        Returns:
            Template string
        """
        if self._template_input is None:
            return ""
        return self._template_input.text()

    def set_template(self, template: str) -> None:
        """
        Set template string.

        Args:
            template: Template string to set
        """
        if self._template_input is not None:
            self._template_input.setText(template)

    def validate(self) -> tuple[bool, str]:
        """
        Validate current template.

        Returns:
            Tuple of (is_valid, error_message)
        """
        template_str = self.get_template()

        if not template_str:
            return False, "Template cannot be empty"

        try:
            template = NamingTemplate(template_str)
            return template.validate()
        except Exception as e:
            return False, str(e)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dictionary for state persistence.

        Returns:
            Dictionary with 'template' key
        """
        return {
            "template": self.get_template(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore from dictionary.

        Args:
            data: Dictionary with 'template' key
        """
        template = data.get("template", "")
        self.set_template(template)
