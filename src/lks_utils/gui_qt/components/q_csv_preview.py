"""Qt component for previewing CSV/tabular data."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class QCSVPreviewComponent(QWidget):
    """Component for previewing CSV/tabular data in a read-only table.

    Features:
    - Read-only table display
    - Optional refresh button
    - Configurable row limit for preview
    - Column auto-sizing
    - Row count indicator

    Signals:
    - refresh_requested: Emitted when refresh button is clicked
    """

    refresh_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "Preview",
        show_refresh: bool = True,
        max_preview_rows: int = 100,
        min_height: int = 300,
    ) -> None:
        """Initialize CSV preview component.

        Args:
            parent: Parent widget
            title: Title for the preview group box
            show_refresh: Show refresh button
            max_preview_rows: Maximum number of rows to display
            min_height: Minimum height of table in pixels
        """
        super().__init__(parent)

        self._max_preview_rows = max_preview_rows
        self._total_rows = 0
        self._show_refresh = show_refresh

        # Build UI
        self._build_ui(title, min_height)

    def _build_ui(self, title: str, min_height: int) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Group box container
        group = QGroupBox(title)
        group_layout = QVBoxLayout()
        group_layout.setSpacing(5)

        # Header row with row count and refresh button
        header_row = QHBoxLayout()

        self._row_count_label = QLabel("No data")
        header_row.addWidget(self._row_count_label)

        header_row.addStretch()

        if self._show_refresh:
            self._refresh_btn = QPushButton("Refresh")
            self._refresh_btn.clicked.connect(self.refresh_requested.emit)
            header_row.addWidget(self._refresh_btn)

        group_layout.addLayout(header_row)

        # Table
        self._table = QTableWidget()
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(min_height)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)

        # Row sizing
        self._table.verticalHeader().setDefaultSectionSize(25)
        self._table.verticalHeader().setVisible(False)

        group_layout.addWidget(self._table)

        group.setLayout(group_layout)
        layout.addWidget(group)

    def set_data(
        self,
        headers: list[str],
        rows: list[list[Any]],
        truncated: bool = False,
    ) -> None:
        """Set data to display in preview table.

        Args:
            headers: Column headers
            rows: Data rows (list of lists)
            truncated: Whether rows were truncated to max_preview_rows
        """
        self._total_rows = len(rows)

        # Clear existing data
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)

        if not headers or not rows:
            self._row_count_label.setText("No data")
            return

        # Set up table
        self._table.setColumnCount(len(headers))
        self._table.setHorizontalHeaderLabels(headers)

        # Limit rows for preview
        display_rows = rows[: self._max_preview_rows]
        self._table.setRowCount(len(display_rows))

        # Populate data
        for row_idx, row_data in enumerate(display_rows):
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(
                    str(value) if value is not None else "")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row_idx, col_idx, item)

        # Update row count label
        if truncated or self._total_rows > self._max_preview_rows:
            shown = min(len(display_rows), self._max_preview_rows)
            self._row_count_label.setText(
                f"Showing {shown} of {self._total_rows} rows (preview limited)"
            )
        else:
            self._row_count_label.setText(f"{self._total_rows} rows")

        # Auto-resize columns to content
        self._table.resizeColumnsToContents()

    def clear(self) -> None:
        """Clear the preview table."""
        self._table.clear()
        self._table.setRowCount(0)
        self._table.setColumnCount(0)
        self._row_count_label.setText("No data")

    def set_title(self, title: str) -> None:
        """Update the group box title.

        Args:
            title: New title text
        """
        group = self.findChild(QGroupBox)
        if group:
            group.setTitle(title)

    @property
    def table_widget(self) -> QTableWidget:
        """Access the underlying QTableWidget for advanced customization."""
        return self._table
