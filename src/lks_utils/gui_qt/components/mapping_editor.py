"""Mapping editor component for key-value pair management."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme import COLORS


class QMappingEditorComponent(QWidget):
    """Component for editing key-value mappings.

    Features:
    - Table display of key-value pairs
    - Add/update/remove mappings
    - Selection handling
    - Read-only keys or editable keys mode
    - Export/import to/from dict

    Signals:
    - mapping_changed: Emitted when mapping is modified
    """

    mapping_changed = Signal(dict)  # {key: value}

    def __init__(
        self,
        parent: QWidget | None = None,
        key_label: str = "Key",
        value_label: str = "Value",
        key_editable: bool = True,
        show_buttons: bool = True,
        height: int = 300,
        value_options: list[str] | None = None,
    ) -> None:
        """Initialize mapping editor.

        Args:
            parent: Parent widget
            key_label: Label for key column
            value_label: Label for value column
            key_editable: Whether keys can be edited (False for fixed keys like identifiers)
            show_buttons: Show add/update/remove buttons
            height: Minimum height of table in pixels
            value_options: Optional list of valid values for dropdown selection (enables enum mode)
        """
        super().__init__(parent)

        self._key_label = key_label
        self._value_label = value_label
        self._key_editable = key_editable
        self._show_buttons = show_buttons
        self._height = height
        self._value_options = value_options

        # State
        self._mappings: dict[str, str] = {}

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # --- Button Row ---
        if self._show_buttons:
            btn_frame = QWidget()
            btn_layout = QHBoxLayout(btn_frame)
            btn_layout.setContentsMargins(0, 0, 0, 0)

            self._btn_add = QPushButton("Add Row")
            self._btn_add.clicked.connect(self._add_blank_row)
            btn_layout.addWidget(self._btn_add)

            self._btn_remove = QPushButton("Remove Selected")
            self._btn_remove.clicked.connect(self._remove_selected)
            btn_layout.addWidget(self._btn_remove)

            self._btn_clear = QPushButton("Clear All")
            self._btn_clear.clicked.connect(self._clear_all_mappings)
            btn_layout.addWidget(self._btn_clear)

            btn_layout.addStretch()

            layout.addWidget(btn_frame)

        # --- Table ---
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(
            [self._key_label, self._value_label])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self._table.setMinimumHeight(self._height)

        # Cell editing
        self._table.itemChanged.connect(self._on_item_changed)
        self._updating_table = False  # Flag to prevent recursive updates

        # Enable Delete key
        self._table.keyPressEvent = self._on_table_key_press

        layout.addWidget(self._table, stretch=1)

        # --- Info Label ---
        self._lbl_info = QLabel("0 mappings")
        self._lbl_info.setStyleSheet(
            f"color: {COLORS['light']}; font-size: 10px;")
        layout.addWidget(self._lbl_info)

    def _add_blank_row(self) -> None:
        """Add a blank row for user to fill in."""
        # Find a unique temporary key
        temp_key = "new_key"
        counter = 1
        while temp_key in self._mappings:
            temp_key = f"new_key_{counter}"
            counter += 1

        # Add blank mapping
        self._mappings[temp_key] = ""
        self._update_table()

        # Find and select the new row, start editing the key
        for i in range(self._table.rowCount()):
            if self._table.item(i, 0).text() == temp_key:
                self._table.selectRow(i)
                self._table.editItem(self._table.item(i, 0))
                break

        self.mapping_changed.emit(self._mappings.copy())

    def _remove_selected(self) -> None:
        """Remove selected rows."""
        selected_rows = sorted(
            set(index.row() for index in self._table.selectedIndexes()), reverse=True)

        if not selected_rows:
            return

        # Get keys to remove
        keys_to_remove = []
        for row in selected_rows:
            key_item = self._table.item(row, 0)
            if key_item:
                keys_to_remove.append(key_item.text())

        # Remove from mappings
        for key in keys_to_remove:
            if key in self._mappings:
                del self._mappings[key]

        self._update_table()
        self.mapping_changed.emit(self._mappings.copy())

    def _clear_all_mappings(self) -> None:
        """Clear all mappings."""
        self._mappings.clear()
        self._update_table()
        self.mapping_changed.emit(self._mappings.copy())

    def _update_table(self) -> None:
        """Update table display."""
        self._updating_table = True  # Block itemChanged signals
        self._table.setRowCount(0)

        for idx, (key, value) in enumerate(sorted(self._mappings.items())):
            self._table.insertRow(idx)

            key_item = QTableWidgetItem(key)

            # Make key read-only if not editable
            if not self._key_editable:
                key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
                key_item.setBackground(QColor(COLORS['secondary']))

            self._table.setItem(idx, 0, key_item)

            # Use dropdown if value_options provided, otherwise text cell
            if self._value_options:
                combo = QComboBox()
                combo.addItems([""] + self._value_options)
                combo.setCurrentText(value)
                combo.currentTextChanged.connect(
                    lambda text, k=key: self._on_combo_changed(k, text)
                )
                self._table.setCellWidget(idx, 1, combo)
            else:
                value_item = QTableWidgetItem(value)
                self._table.setItem(idx, 1, value_item)

        self._updating_table = False  # Re-enable itemChanged signals
        self._update_info_label()

    def _update_info_label(self) -> None:
        """Update the info label with current mapping count."""
        count = len(self._mappings)
        self._lbl_info.setText(f"{count} mapping{'s' if count != 1 else ''}")

    def _on_table_key_press(self, event) -> None:
        """Handle key press events in table."""
        if event.key() == Qt.Key_Delete:
            self._remove_selected()
        else:
            # Call original keyPressEvent
            QTableWidget.keyPressEvent(self._table, event)

    def _on_combo_changed(self, key: str, value: str) -> None:
        """Handle dropdown value change."""
        if self._updating_table:
            return

        self._mappings[key] = value
        self._update_info_label()
        self.mapping_changed.emit(self._mappings.copy())

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """Handle cell edit in table."""
        if self._updating_table:
            return  # Ignore changes during programmatic updates

        row = item.row()
        col = item.column()

        # Skip if this row uses dropdown for values
        if self._value_options and col == 1:
            return  # Value changes handled by _on_combo_changed

        key_item = self._table.item(row, 0)
        value_widget = self._table.cellWidget(
            row, 1) if self._value_options else None
        value_item = self._table.item(
            row, 1) if not self._value_options else None

        if not key_item:
            return
        if not self._value_options and not value_item:
            return

        old_key = list(sorted(self._mappings.keys()))[row]
        new_key = key_item.text().strip()

        # Get value from combo widget (enum mode) or text cell
        if self._value_options and value_widget:
            new_value = value_widget.currentText()
        elif value_item:
            new_value = value_item.text().strip()
        else:
            new_value = self._mappings.get(old_key, "")

        # Validate key is not empty
        if col == 0 and not new_key:
            self._updating_table = True
            key_item.setText(old_key)  # Restore old key
            self._updating_table = False
            return

        # Check for duplicate key if key changed
        if col == 0 and new_key != old_key:
            if new_key in self._mappings:
                self._updating_table = True
                key_item.setText(old_key)  # Restore old key
                self._updating_table = False
                return

            # Update key
            del self._mappings[old_key]
            self._mappings[new_key] = new_value
        else:
            # Update value only
            self._mappings[old_key] = new_value

        # Close any active editor before rebuilding table
        self._table.closePersistentEditor(item)

        # Refresh table to maintain sorted order
        current_key = new_key if col == 0 else old_key
        self._update_table()

        # Restore selection to edited item
        for i in range(self._table.rowCount()):
            if self._table.item(i, 0).text() == current_key:
                self._table.selectRow(i)
                break

        self.mapping_changed.emit(self._mappings.copy())

    def set_mappings(self, mappings: dict[str, str]) -> None:
        """Set all mappings.

        Args:
            mappings: Dictionary of key-value pairs
        """
        self._mappings = mappings.copy()
        self._update_table()

    def get_mappings(self) -> dict[str, str]:
        """Get all mappings.

        Returns:
            Dictionary of key-value pairs
        """
        return self._mappings.copy()

    def add_mapping(self, key: str, value: str) -> None:
        """Add or update a single mapping programmatically.

        Args:
            key: Mapping key
            value: Mapping value
        """
        self._mappings[key] = value
        self._update_table()
        self.mapping_changed.emit(self._mappings.copy())

    def remove_mapping(self, key: str) -> None:
        """Remove a mapping by key.

        Args:
            key: Mapping key to remove
        """
        if key in self._mappings:
            del self._mappings[key]
            self._update_table()
            self.mapping_changed.emit(self._mappings.copy())

    def has_mapping(self, key: str) -> bool:
        """Check if a mapping exists.

        Args:
            key: Mapping key to check

        Returns:
            True if mapping exists
        """
        return key in self._mappings

    def get_mapping(self, key: str, default: str = "") -> str:
        """Get value for a key.

        Args:
            key: Mapping key
            default: Default value if key not found

        Returns:
            Mapping value or default
        """
        return self._mappings.get(key, default)

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        return {
            "mappings": self._mappings.copy(),
        }

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        if "mappings" in state:
            self.set_mappings(state["mappings"])
