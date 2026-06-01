"""Qt Data Table Widget - Reusable table with sorting and resizing.

Provides a QTableWidget with common features:
- Column sorting (click headers)
- Column resizing (drag headers)
- Optional row numbers
- Alternating row colors
- Multiple selection modes
- Typed columns with automatic formatting
- Validation for typed columns
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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QMessageBox,
)
from PySide6.QtCore import Qt, Signal

from lks_utils.gui_qt.widgets.data_table.column_types import ColumnDefinition, ColumnType


class QDataTableWidget(QTableWidget):
    """Enhanced table widget with sorting and resizing.

    Features:
    - Click column headers to sort
    - Drag column borders to resize
    - Optional row numbers
    - Alternating row colors
    - Customizable selection modes
    - Row autosizing options
    - Editable/read-only modes
    - Smart text eliding (shows "..." at clip point)
    - Typed columns (int, float, currency, bool) with auto-formatting
    - Input validation for typed columns

    Signals:
        selectionChanged: Emitted when selection changes (inherited)

    Example:
        # Simple string columns
        table = QDataTableWidget(
            columns=["Name", "Age", "Email"],
            sortable=True,
            editable=False
        )

        # Typed columns with formatting
        from lks_utils.gui_qt.widgets.column_types import ColumnDefinition, ColumnType

        table = QDataTableWidget(
            columns=[
                ColumnDefinition("Product", ColumnType.STRING),
                ColumnDefinition("Price", ColumnType.CURRENCY, decimals=2),
                ColumnDefinition("Quantity", ColumnType.INT),
                ColumnDefinition("In Stock", ColumnType.BOOL)
            ],
            editable=True
        )

        # Add row (values auto-format based on column type)
        table.add_row(["Widget", 19.99, 5, True])  # Displays as "Widget", "$19.99", "5", "✓"
    """

    def __init__(
        self,
        columns: Union[list[str], list[ColumnDefinition]],
        sortable: bool = True,
        show_row_numbers: bool = False,
        selection_mode: QAbstractItemView.SelectionMode = QAbstractItemView.ExtendedSelection,
        editable: bool = False,
        row_resize_mode: QHeaderView.ResizeMode = QHeaderView.ResizeMode.ResizeToContents,
        allow_rename_columns: bool = False,
        allow_change_types: bool = False,
        parent: QTableWidget | None = None
    ):
        """Initialize the data table.

        Args:
            columns: List of column names (str) or ColumnDefinition objects for typed columns
            sortable: Enable column sorting by clicking headers
            show_row_numbers: Show row number column on left
            selection_mode: Selection mode (single, multi, extended, etc.)
            editable: Whether cells are editable by default (can override per-row/column)
            row_resize_mode: Row height adjustment (ResizeToContents, Fixed, Interactive)
            allow_rename_columns: Allow renaming columns via double-click or context menu
            allow_change_types: Allow changing column types via context menu
            parent: Parent widget
        """
        super().__init__(parent)

        # Convert string columns to ColumnDefinition objects
        self._column_defs: list[ColumnDefinition] = []
        for col in columns:
            if isinstance(col, str):
                self._column_defs.append(ColumnDefinition(
                    name=col, type=ColumnType.STRING, editable=editable))
            else:
                self._column_defs.append(col)

        self._sortable = sortable
        self._editable = editable
        self._allow_rename_columns = allow_rename_columns
        self._allow_change_types = allow_change_types

        self._setup_table(show_row_numbers, selection_mode, row_resize_mode)

    def _setup_table(self, show_row_numbers: bool, selection_mode: QAbstractItemView.SelectionMode, row_resize_mode: QHeaderView.ResizeMode):
        """Setup table properties."""
        # Set columns
        self.setColumnCount(len(self._column_defs))
        self.setHorizontalHeaderLabels([col.name for col in self._column_defs])

        # Selection
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(selection_mode)

        # Appearance
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(show_row_numbers)

        # Sorting
        if self._sortable:
            self.setSortingEnabled(True)

        # Column resizing - allow user to drag
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        # Set minimum column widths for better text display
        for i in range(len(self._column_defs)):
            # Increased from 50 for better text visibility
            header.setMinimumSectionSize(80)

        # Row resizing
        v_header = self.verticalHeader()
        v_header.setSectionResizeMode(row_resize_mode)

        # Better text eliding - show ellipsis at actual clip point
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)

        # Connect item changed signal for validation
        self.itemChanged.connect(self._on_item_changed)

        # Setup header interactions
        if self._allow_rename_columns or self._allow_change_types:
            header.setContextMenuPolicy(Qt.CustomContextMenu)
            header.customContextMenuRequested.connect(
                self._show_header_context_menu)

            if self._allow_rename_columns:
                header.sectionDoubleClicked.connect(self._rename_column_header)

    def add_row(
        self,
        data: list[Any],
        user_data: Any = None,
        editable: bool | None = None
    ) -> int:
        """Add a row to the table.

        Args:
            data: List of values for each column (will be formatted based on column type)
            user_data: Optional data to store with the row (in first column)
            editable: Whether cells should be editable (None = use column/table default)

        Returns:
            Row index of added row
        """
        row = self.rowCount()
        self.insertRow(row)

        # Use row-specific editable if provided
        row_editable = editable if editable is not None else self._editable

        # Temporarily disconnect itemChanged to avoid validation during setup
        self.itemChanged.disconnect(self._on_item_changed)

        for col, value in enumerate(data):
            if col >= len(self._column_defs):
                break

            col_def = self._column_defs[col]

            # Format value based on column type
            formatted_text = col_def.format_value(value)
            item = QTableWidgetItem(formatted_text)

            # Store raw value in UserRole for retrieval
            item.setData(Qt.UserRole, value if col >
                         0 or user_data is None else user_data)
            if user_data is not None and col == 0:
                # Store user_data in a separate role
                item.setData(Qt.UserRole + 1, user_data)

            # Set editable flag based on column definition and row override
            cell_editable = col_def.editable if row_editable else False
            if not cell_editable:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)

            self.setItem(row, col, item)

        # Reconnect validation
        self.itemChanged.connect(self._on_item_changed)

        return row

    def _on_item_changed(self, item: QTableWidgetItem):
        """Validate and format cell value when changed.

        Args:
            item: The changed table item
        """
        col = item.column()
        if col < 0 or col >= len(self._column_defs):
            return

        col_def = self._column_defs[col]
        text = item.text()

        # Parse and validate
        valid, parsed_value, error_msg = col_def.parse_value(text)

        if not valid:
            # Show error and revert
            QMessageBox.warning(
                self,
                "Invalid Input",
                f"Invalid value for {col_def.name}:\n{error_msg}"
            )
            # Revert to previous value stored in UserRole
            old_value = item.data(Qt.UserRole)
            self.itemChanged.disconnect(self._on_item_changed)
            item.setText(col_def.format_value(old_value))
            self.itemChanged.connect(self._on_item_changed)
        else:
            # Update stored value and reformat
            item.setData(Qt.UserRole, parsed_value)
            self.itemChanged.disconnect(self._on_item_changed)
            item.setText(col_def.format_value(parsed_value))
            self.itemChanged.connect(self._on_item_changed)

    def update_row(self, row: int, data: list[str]):
        """Update an existing row.

        Args:
            row: Row index
            data: List of values for each column
        """
        if row < 0 or row >= self.rowCount():
            return

        for col, value in enumerate(data):
            if col < self.columnCount():
                item = self.item(row, col)
                if item:
                    item.setText(str(value))

    def get_row_data(self, row: int, typed: bool = False) -> Union[list[str], list[Any]]:
        """Get data from a specific row.

        Args:
            row: Row index
            typed: If True, return typed values; if False, return formatted strings

        Returns:
            List of cell values (strings or typed values)
        """
        if row < 0 or row >= self.rowCount():
            return []

        if typed:
            # Return typed values from UserRole
            data: list[Any] = []
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    # Get typed value from UserRole
                    value = item.data(Qt.UserRole)
                    data.append(value)
                else:
                    data.append(None)
            return data
        else:
            # Return formatted text
            data: list[str] = []
            for col in range(self.columnCount()):
                item = self.item(row, col)
                data.append(item.text() if item else "")
            return data

    def get_row_user_data(self, row: int) -> Any:
        """Get user data from a specific row.

        Args:
            row: Row index

        Returns:
            User data stored in first column, or None
        """
        if row < 0 or row >= self.rowCount():
            return None

        item = self.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def get_selected_rows(self) -> list[int]:
        """Get indices of selected rows.

        Returns:
            List of row indices
        """
        selected_items = self.selectedItems()
        rows = set()
        for item in selected_items:
            rows.add(item.row())
        return sorted(rows)

    def get_selected_row_data(self) -> list[list[str]]:
        """Get data from all selected rows.

        Returns:
            List of row data (each row is a list of cell values)
        """
        rows = self.get_selected_rows()
        return [self.get_row_data(row) for row in rows]

    def get_selected_user_data(self) -> list[Any]:
        """Get user data from all selected rows.

        Returns:
            List of user data objects
        """
        rows = self.get_selected_rows()
        return [self.get_row_user_data(row) for row in rows]

    def remove_row(self, row: int):
        """Remove a specific row.

        Args:
            row: Row index to remove
        """
        if 0 <= row < self.rowCount():
            self.removeRow(row)

    def remove_selected_rows(self):
        """Remove all selected rows."""
        rows = self.get_selected_rows()
        # Remove in reverse order to maintain indices
        for row in reversed(rows):
            self.removeRow(row)

    def clear_data(self):
        """Clear all rows but keep headers."""
        self.setRowCount(0)

    def set_column_widths(self, widths: dict[str, int]):
        """Set specific column widths.

        Args:
            widths: Dictionary of column_name -> width_pixels
        """
        for col_idx, col_name in enumerate(self._columns):
            if col_name in widths:
                self.setColumnWidth(col_idx, widths[col_name])

    def resize_rows_to_contents(self):
        """Manually trigger row resize to fit contents.

        Useful when row_resize_mode is not ResizeToContents but you want
        to adjust specific rows programmatically.
        """
        self.resizeRowsToContents()

    def resize_columns_to_contents(self):
        """Manually trigger column resize to fit contents."""
        self.resizeColumnsToContents()

    def set_editable(self, editable: bool):
        """Change editable mode for all existing cells.

        Args:
            editable: Whether cells should be editable
        """
        self._editable = editable
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    if editable:
                        item.setFlags(item.flags() | Qt.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() & ~Qt.ItemIsEditable)

    def _show_header_context_menu(self, position):
        """Show context menu on header right-click.

        Args:
            position: Click position
        """
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QAction

        header = self.horizontalHeader()
        col = header.logicalIndexAt(position)

        if col < 0:
            return

        menu = QMenu(self)

        # Rename action
        rename_action = QAction("Rename Column", self)
        rename_action.triggered.connect(
            lambda: self._rename_column_header(col))
        rename_action.setEnabled(self._allow_rename_columns)
        menu.addAction(rename_action)

        # Change type action
        change_type_action = QAction("Change Data Type...", self)
        change_type_action.triggered.connect(
            lambda: self._change_column_type(col))
        change_type_action.setEnabled(self._allow_change_types)
        menu.addAction(change_type_action)

        # Show menu at cursor
        menu.exec(header.mapToGlobal(position))

    def _rename_column_header(self, col: int):
        """Rename a column header.

        Args:
            col: Column index
        """
        from PySide6.QtWidgets import QInputDialog

        if not self._allow_rename_columns or col < 0 or col >= len(self._column_defs):
            return

        old_name = self._column_defs[col].name

        new_name, ok = QInputDialog.getText(
            self,
            "Rename Column",
            "Enter new column name:",
            text=old_name
        )

        if ok and new_name and new_name != old_name:
            # Update column definition
            self._column_defs[col].name = new_name
            # Update header label
            self.horizontalHeaderItem(col).setText(new_name)

    def _change_column_type(self, col: int):
        """Change column data type with preview.

        Args:
            col: Column index
        """
        if not self._allow_change_types or col < 0 or col >= len(self._column_defs):
            return

        # Import dialog (will create next)
        from lks_utils.gui_qt.widgets.data_table.type_conversion_dialog import QTypeConversionDialog

        current_def = self._column_defs[col]

        # Get all current values in this column
        values = []
        for row in range(self.rowCount()):
            item = self.item(row, col)
            if item:
                values.append(item.data(Qt.UserRole))
            else:
                values.append(None)

        # Show conversion dialog
        dialog = QTypeConversionDialog(
            column_name=current_def.name,
            current_type=current_def.type,
            current_values=values,
            parent=self
        )

        if dialog.exec():
            # Apply conversion
            new_def, converted_values = dialog.get_result()

            # Update column definition
            self._column_defs[col] = new_def

            # Temporarily disconnect validation
            self.itemChanged.disconnect(self._on_item_changed)

            # Update all cells in this column
            for row, value in enumerate(converted_values):
                if row < self.rowCount():
                    formatted_text = new_def.format_value(value)
                    item = self.item(row, col)
                    if item:
                        item.setText(formatted_text)
                        item.setData(Qt.UserRole, value)

            # Reconnect validation
            self.itemChanged.connect(self._on_item_changed)
