"""Type Conversion Dialog for QDataTableWidget.

Shows preview of type conversion with error highlighting.
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
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QRadioButton,
    QButtonGroup,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QGroupBox,
    QTextEdit,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from lks_utils.gui_qt.widgets.data_table.column_types import ColumnDefinition, ColumnType
from lks_utils.gui_qt.widgets.data_table.type_conversion import (
    ConversionMode,
    convert_value,
    can_convert,
)


class QTypeConversionDialog(QDialog):
    """Dialog for converting column data type with live preview.

    Shows:
    - Target type selector
    - Conversion mode (Clear/Preserve/Unit Convert)
    - Warning message
    - Live preview table with before/after
    - Error cells highlighted in red
    """

    def __init__(
        self,
        column_name: str,
        current_type: ColumnType,
        current_values: list[Any],
        parent=None
    ):
        super().__init__(parent)

        self._column_name = column_name
        self._current_type = current_type
        self._current_values = current_values
        self._converted_values: list[Any] = []
        self._conversion_errors: list[bool] = []

        self._setup_ui()
        self._update_preview()

    def _setup_ui(self):
        """Setup dialog UI."""
        self.setWindowTitle(f"Change Column Type: {self._column_name}")
        self.resize(700, 600)

        layout = QVBoxLayout(self)

        # Header info
        info_label = QLabel(
            f"<b>Column:</b> {self._column_name}<br>"
            f"<b>Current Type:</b> {self._current_type.value.title()}<br>"
            f"<b>Rows:</b> {len(self._current_values)}"
        )
        layout.addWidget(info_label)

        # Target type selector
        type_group = QGroupBox("Target Type")
        type_layout = QHBoxLayout(type_group)

        type_layout.addWidget(QLabel("Convert to:"))
        self.type_combo = QComboBox()
        for col_type in ColumnType:
            self.type_combo.addItem(col_type.value.title(), col_type)
        # Set current type as default
        self.type_combo.setCurrentText(self._current_type.value.title())
        self.type_combo.currentIndexChanged.connect(self._update_preview)
        type_layout.addWidget(self.type_combo)
        type_layout.addStretch()

        layout.addWidget(type_group)

        # Conversion mode
        mode_group = QGroupBox("Conversion Mode")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_button_group = QButtonGroup()

        self.clear_radio = QRadioButton("Clear All Data")
        self.clear_radio.setToolTip("Remove all values from this column")
        self.mode_button_group.addButton(self.clear_radio, 0)
        mode_layout.addWidget(self.clear_radio)

        self.preserve_radio = QRadioButton("Preserve Values")
        self.preserve_radio.setToolTip(
            "Keep literal values (11→11.0, '11'→11). Unconvertible values will be cleared.")
        self.preserve_radio.setChecked(True)
        self.mode_button_group.addButton(self.preserve_radio, 1)
        mode_layout.addWidget(self.preserve_radio)

        self.unit_radio = QRadioButton("Unit Conversion")
        self.unit_radio.setToolTip("Smart conversion (cents→dollars, etc.)")
        self.mode_button_group.addButton(self.unit_radio, 2)
        mode_layout.addWidget(self.unit_radio)

        # Connect mode changes to preview update
        self.mode_button_group.buttonClicked.connect(self._update_preview)

        layout.addWidget(mode_group)

        # Warning message
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet(
            "QLabel { color: #ff9800; font-style: italic; }")
        layout.addWidget(self.warning_label)

        # Preview table
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(2)
        self.preview_table.setHorizontalHeaderLabels(
            ["Current Value", "Converted Value"])
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QTableWidget.SelectRows)

        # Show first 100 rows max
        max_preview = min(100, len(self._current_values))
        self.preview_table.setRowCount(max_preview)

        if len(self._current_values) > 100:
            preview_note = QLabel(
                f"<i>Showing first 100 of {len(self._current_values)} rows</i>")
            preview_layout.addWidget(preview_note)

        preview_layout.addWidget(self.preview_table)
        layout.addWidget(preview_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _get_selected_mode(self) -> ConversionMode:
        """Get currently selected conversion mode."""
        if self.clear_radio.isChecked():
            return ConversionMode.CLEAR
        elif self.preserve_radio.isChecked():
            return ConversionMode.PRESERVE
        else:
            return ConversionMode.UNIT_CONVERT

    def _update_preview(self):
        """Update preview table with converted values."""
        target_type = self.type_combo.currentData()
        mode = self._get_selected_mode()

        if target_type is None:
            return

        # Check for warnings
        can_do, warning = can_convert(self._current_type, target_type, mode)
        if warning:
            self.warning_label.setText(f"⚠️ {warning}")
            self.warning_label.setVisible(True)
        else:
            self.warning_label.setVisible(False)

        # Create temporary column definition for formatting
        temp_def = ColumnDefinition(name=self._column_name, type=target_type)

        # Convert all values
        self._converted_values = []
        self._conversion_errors = []

        for value in self._current_values:
            result = convert_value(
                value, self._current_type, target_type, mode)
            self._converted_values.append(result.value)
            self._conversion_errors.append(not result.success)

        # Update preview table (first 100 rows)
        max_preview = min(100, len(self._current_values))
        for row in range(max_preview):
            # Current value
            current_text = str(
                self._current_values[row]) if self._current_values[row] is not None else ""
            current_item = QTableWidgetItem(current_text)
            current_item.setFlags(current_item.flags() & ~Qt.ItemIsEditable)
            self.preview_table.setItem(row, 0, current_item)

            # Converted value
            converted_val = self._converted_values[row]
            converted_text = temp_def.format_value(converted_val)
            converted_item = QTableWidgetItem(converted_text)
            converted_item.setFlags(
                converted_item.flags() & ~Qt.ItemIsEditable)

            # Highlight errors in red
            if self._conversion_errors[row]:
                converted_item.setBackground(QColor("#d32f2f"))
                converted_item.setForeground(QColor("#ffffff"))
                converted_item.setToolTip(
                    "Conversion failed - value will be cleared")

            self.preview_table.setItem(row, 1, converted_item)

        # Resize columns to content
        self.preview_table.resizeColumnsToContents()

        # Update warning with error count
        error_count = sum(self._conversion_errors)
        if error_count > 0:
            existing_warning = self.warning_label.text()
            error_msg = f"\n❌ {error_count} value(s) cannot be converted and will be cleared."
            if existing_warning:
                self.warning_label.setText(existing_warning + error_msg)
            else:
                self.warning_label.setText(error_msg)
                self.warning_label.setVisible(True)

    def get_result(self) -> tuple[ColumnDefinition, list[Any]]:
        """Get conversion result.

        Returns:
            Tuple of (new_column_definition, converted_values)
        """
        target_type = self.type_combo.currentData()

        # Create new column definition
        new_def = ColumnDefinition(
            name=self._column_name,
            type=target_type,
            editable=True,  # Preserve editability from original
        )

        return new_def, self._converted_values
