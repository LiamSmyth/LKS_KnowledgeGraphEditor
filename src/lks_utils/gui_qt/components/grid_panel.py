"""
QGridPanel - Evenly distributed grid layout widget for UI elements.

Provides a simple grid that arranges widgets with configurable alignment,
spacing, and optional fixed or fractional column/row sizing.
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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QSizePolicy,
    QWidget,
)


class QGridPanel(QWidget):
    """
    Simple grid layout widget for evenly distributing UI elements.

    Arranges widgets in a grid with configurable:
    - Column count (auto-wrap behavior)
    - Per-cell alignment (horizontal + vertical)
    - Uniform padding and spacing
    - Optional fixed/fractional column/row sizing
    - Optional uniform minimum sizes for cells

    **Interface**:
    - `add_widget(widget, alignment=Qt.AlignCenter)` → add to next cell
    - `add_stretch(cols=1, rows=1)` → add empty stretch cells
    - `set_column_stretch(col, stretch)` → set column weight
    - `set_row_stretch(row, stretch)` → set row weight
    - `set_column_minimum_width(col, width)` → set minimum width
    - `set_row_minimum_height(row, height)` → set minimum height
    - `to_dict() / from_dict()` → state persistence (layout state only)

    **Example**:
    ```python
    # 3-column grid with labels and inputs side-by-side
    grid = QGridPanel(
        columns=3,
        spacing=8,
        padding=(10, 10, 10, 10),
        uniform_item_height=30,
    )

    # Add items (auto-wraps to 3 columns)
    grid.add_widget(QLabel("Name:"))
    grid.add_widget(QLineEdit())
    grid.add_widget(QLabel("Value:"))

    grid.add_widget(QLabel("Format:"))
    grid.add_widget(QComboBox())
    grid.add_widget(QPushButton("Browse"))

    # Optional: set all columns equally weighted
    for col in range(3):
        grid.set_column_stretch(col, 1)
    ```
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        columns: int = 2,
        spacing: int = 6,
        padding: tuple[int, int, int, int] = (10, 10, 10, 10),
        uniform_item_height: int | None = None,
        uniform_item_width: int | None = None,
    ) -> None:
        """
        Initialize grid panel.

        Args:
            parent: Parent widget.
            columns: Number of columns before wrapping.
            spacing: Space between items (pixels).
            padding: Content margins (left, top, right, bottom).
            uniform_item_height: Optional fixed height for all items (0 = natural).
            uniform_item_width: Optional fixed width for all items (0 = natural).
        """
        super().__init__(parent)

        self._columns = columns
        self._uniform_height = uniform_item_height
        self._uniform_width = uniform_item_width
        self._item_count = 0
        self._column_stretches: dict[int, int] = {}
        self._row_stretches: dict[int, int] = {}
        self._column_min_widths: dict[int, int] = {}
        self._row_min_heights: dict[int, int] = {}

        # Create layout
        self.grid_layout = QGridLayout(self)
        self.grid_layout.setSpacing(spacing)
        self.grid_layout.setContentsMargins(*padding)

    def add_widget(
        self,
        widget: QWidget,
        alignment: Qt.AlignmentFlag | None = None,
    ) -> None:
        """
        Add a widget to the next available cell.

        Automatically wraps to the next row after `columns` items.

        Args:
            widget: Widget to add.
            alignment: Cell alignment (defaults to top-left).
        """
        if alignment is None:
            alignment = Qt.AlignmentFlag(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        row = self._item_count // self._columns
        col = self._item_count % self._columns

        self.grid_layout.addWidget(
            widget,
            row,
            col,
            alignment=alignment,
        )

        # Apply uniform sizing if configured
        if self._uniform_height is not None and self._uniform_height > 0:
            widget.setFixedHeight(self._uniform_height)
        if self._uniform_width is not None and self._uniform_width > 0:
            widget.setFixedWidth(self._uniform_width)

        # Apply any previously-set stretches
        if col in self._column_stretches:
            self.grid_layout.setColumnStretch(col, self._column_stretches[col])
        if row in self._row_stretches:
            self.grid_layout.setRowStretch(row, self._row_stretches[row])

        # Apply any previously-set minimum sizes
        if col in self._column_min_widths:
            self.grid_layout.setColumnMinimumWidth(
                col, self._column_min_widths[col])
        if row in self._row_min_heights:
            self.grid_layout.setRowMinimumHeight(
                row, self._row_min_heights[row])

        self._item_count += 1

    def add_stretch(self, cols: int = 1, rows: int = 1) -> None:
        """
        Add empty stretch cell(s) to the grid.

        Useful for spacing or filling gaps.

        Args:
            cols: Number of columns to span.
            rows: Number of rows to span.
        """
        row = self._item_count // self._columns
        col = self._item_count % self._columns

        # Create an empty stretch widget
        stretch_widget = QWidget()
        stretch_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.grid_layout.addWidget(stretch_widget, row, col, rows, cols)
        self._item_count += cols * rows

    def set_column_stretch(self, col: int, stretch: int) -> None:
        """
        Set horizontal stretch factor for a column.

        Args:
            col: Column index (0-based).
            stretch: Stretch weight (0 = fixed size, 1+ = proportional).
        """
        self._column_stretches[col] = stretch
        self.grid_layout.setColumnStretch(col, stretch)

    def set_row_stretch(self, row: int, stretch: int) -> None:
        """
        Set vertical stretch factor for a row.

        Args:
            row: Row index (0-based).
            stretch: Stretch weight (0 = fixed size, 1+ = proportional).
        """
        self._row_stretches[row] = stretch
        self.grid_layout.setRowStretch(row, stretch)

    def set_column_minimum_width(self, col: int, width: int) -> None:
        """
        Set minimum width for a column.

        Args:
            col: Column index.
            width: Minimum width in pixels.
        """
        self._column_min_widths[col] = width
        self.grid_layout.setColumnMinimumWidth(col, width)

    def set_row_minimum_height(self, row: int, height: int) -> None:
        """
        Set minimum height for a row.

        Args:
            row: Row index.
            height: Minimum height in pixels.
        """
        self._row_min_heights[row] = height
        self.grid_layout.setRowMinimumHeight(row, height)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize grid configuration to dict.

        Note: Does not serialize widget content, only layout configuration.

        Returns:
            Dict with current state.
        """
        return {
            "columns": self._columns,
            "column_stretches": self._column_stretches,
            "row_stretches": self._row_stretches,
            "column_min_widths": self._column_min_widths,
            "row_min_heights": self._row_min_heights,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore grid configuration from dict.

        Args:
            data: Dict with state.
        """
        if "column_stretches" in data:
            for col, stretch in data["column_stretches"].items():
                self.set_column_stretch(int(col), stretch)
        if "row_stretches" in data:
            for row, stretch in data["row_stretches"].items():
                self.set_row_stretch(int(row), stretch)
        if "column_min_widths" in data:
            for col, width in data["column_min_widths"].items():
                self.set_column_minimum_width(int(col), width)
        if "row_min_heights" in data:
            for row, height in data["row_min_heights"].items():
                self.set_row_minimum_height(int(row), height)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all widgets in the grid.

        Args:
            enabled: True to enable, False to disable.
        """
        for row in range(self.grid_layout.rowCount()):
            for col in range(self.grid_layout.columnCount()):
                item = self.grid_layout.itemAtPosition(row, col)
                if item and item.widget():
                    item.widget().setEnabled(enabled)


__all__ = ["QGridPanel"]
