"""Overridable Table Widget - QTableWidget with cell override support.

Thin convenience class composing QTableWidget + QCellOverrideMixin.
Drop-in replacement for QTableWidget when per-cell overrides are needed.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHeaderView, QTableWidget

from lks_utils.gui_qt.widgets.data_table.cell_override_mixin import (
    QCellOverrideMixin,
)


class QOverridableTableWidget(QTableWidget, QCellOverrideMixin):
    """QTableWidget with per-cell override support.

    Combines standard QTableWidget functionality with the QCellOverrideMixin
    override layer. Cells can be overridden by the user (double-click + edit)
    and are highlighted with a blue background. Overrides survive table
    repopulation when the caller uses the ``populating()`` context manager.

    Features:
        - Interactive column resizing (drag column borders)
        - Per-cell override detection on user edit
        - Blue highlight for overridden cells
        - Right-click context menu: "Clear Override" / "Clear All Overrides"
        - Delete key clears override on selected cells
        - ``populating()`` context manager for bulk programmatic updates
        - ``get_overrides_dict()`` / ``set_overrides_dict()`` for persistence

    Signals:
        override_changed(int, int, object): Emitted when a cell override is
            set (value=str) or cleared (value=None). Args: row, col, value.

    Example::

        table = QOverridableTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["A", "B", "C"])

        # Programmatic population (no overrides triggered)
        with table.populating():
            for row in range(10):
                table.setRowCount(row + 1)
                for col in range(3):
                    table.setItem(row, col, QTableWidgetItem(f"R{row}C{col}"))

        # User double-clicks cell (0, 1), types "custom", presses Enter
        # → cell turns blue, table.has_override(0, 1) == True

        # Reconnect after regeneration
        table.override_changed.connect(on_override)
    """

    override_changed: Signal = Signal(int, int, object)

    def __init__(self, parent: QTableWidget | None = None) -> None:
        """Initialize the overridable table.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._init_overrides()
        self._setup_interactive_columns()

    def _setup_interactive_columns(self) -> None:
        """Configure interactive column resizing."""
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(60)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key presses, routing Delete to override clearing.

        Args:
            event: The key event.
        """
        if self.override_key_press_event(event):
            return
        super().keyPressEvent(event)
