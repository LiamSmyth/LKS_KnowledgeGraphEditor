"""Dependency table component for displaying package/model status."""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme import COLORS


class QDependencyTableComponent(QWidget):
    """Component for displaying dependency status in a table.

    Features:
    - Table with dependency name, status, version, notes columns
    - Color-coded status indicators (✓/✗/⚠)
    - Refresh button to re-check dependencies
    - Action button per row (install/update)
    - Automatic row styling based on status

    Signals:
    - refresh_clicked: Emitted when refresh button is clicked
    - action_clicked: Emitted when row action button is clicked (dependency_name: str)
    """

    refresh_clicked = Signal()
    action_clicked = Signal(str)  # dependency name

    def __init__(
        self,
        parent: QWidget | None = None,
        show_refresh_button: bool = True,
        show_action_buttons: bool = True,
        height: int = 400,
    ) -> None:
        """Initialize dependency table.

        Args:
            parent: Parent widget
            show_refresh_button: Show refresh button
            show_action_buttons: Show action buttons in rows
            height: Minimum height of table in pixels
        """
        super().__init__(parent)

        self._show_refresh = show_refresh_button
        self._show_actions = show_action_buttons
        self._height = height

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # --- Refresh Button ---
        if self._show_refresh:
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 0, 0, 0)

            self._btn_refresh = QPushButton("Refresh Status")
            self._btn_refresh.clicked.connect(self.refresh_clicked.emit)
            btn_layout.addWidget(self._btn_refresh)

            btn_layout.addStretch()

            layout.addLayout(btn_layout)

        # --- Table ---
        self._table = QTableWidget()
        self._table.setColumnCount(5 if self._show_actions else 4)
        headers = ["Status", "Name", "Version", "Notes"]
        if self._show_actions:
            headers.append("Action")
        self._table.setHorizontalHeaderLabels(headers)

        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Row height for better readability
        self._table.verticalHeader().setDefaultSectionSize(35)
        self._table.verticalHeader().setVisible(True)  # Show row numbers

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Name
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Version
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Notes
        if self._show_actions:
            header.setSectionResizeMode(
                4, QHeaderView.ResizeToContents)  # Action

        self._table.setMinimumHeight(self._height)
        layout.addWidget(self._table, stretch=1)

    def add_dependency(
        self,
        name: str,
        status: Literal["installed", "missing", "warning"] = "installed",
        version: str = "",
        notes: str = "",
        action_label: str = "Install",
    ) -> None:
        """Add a dependency to the table.

        Args:
            name: Dependency name
            status: Status indicator (installed/missing/warning)
            version: Version string
            notes: Additional notes or warnings
            action_label: Label for action button
        """
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Status icon
        status_icons = {
            "installed": "✓",
            "missing": "✗",
            "warning": "⚠",
        }
        status_colors = {
            "installed": COLORS["success"],
            "missing": COLORS["danger"],
            "warning": COLORS["warning"],
        }

        status_item = QTableWidgetItem(status_icons.get(status, "?"))
        status_item.setForeground(
            QColor(status_colors.get(status, COLORS["fg"])))
        status_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, 0, status_item)

        # Name
        name_item = QTableWidgetItem(name)
        self._table.setItem(row, 1, name_item)

        # Version
        version_item = QTableWidgetItem(version)
        self._table.setItem(row, 2, version_item)

        # Notes
        notes_item = QTableWidgetItem(notes)
        if status == "warning":
            notes_item.setForeground(QColor(COLORS["warning"]))
        self._table.setItem(row, 3, notes_item)

        # Action button
        if self._show_actions:
            if status in ["missing", "warning"]:
                btn_action = QPushButton(action_label)
                # Add padding to button content for better appearance
                btn_action.setStyleSheet("padding: 4px 12px;")
                btn_action.clicked.connect(
                    lambda: self.action_clicked.emit(name))
                self._table.setCellWidget(row, 4, btn_action)

    def clear_dependencies(self) -> None:
        """Clear all dependencies from table."""
        self._table.setRowCount(0)

    def set_dependencies(
        self,
        dependencies: list[dict],
    ) -> None:
        """Set all dependencies at once.

        Args:
            dependencies: List of dependency dicts with keys:
                - name: str
                - status: "installed" | "missing" | "warning"
                - version: str (optional)
                - notes: str (optional)
                - action_label: str (optional, default "Install")
        """
        self.clear_dependencies()

        for dep in dependencies:
            self.add_dependency(
                name=dep["name"],
                status=dep.get("status", "installed"),
                version=dep.get("version", ""),
                notes=dep.get("notes", ""),
                action_label=dep.get("action_label", "Install"),
            )

    def get_row_count(self) -> int:
        """Get number of dependencies in table.

        Returns:
            Row count
        """
        return self._table.rowCount()

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        dependencies = []
        for row in range(self._table.rowCount()):
            dep = {
                "name": self._table.item(row, 1).text() if self._table.item(row, 1) else "",
                "version": self._table.item(row, 2).text() if self._table.item(row, 2) else "",
                "notes": self._table.item(row, 3).text() if self._table.item(row, 3) else "",
            }
            # Determine status from icon
            status_item = self._table.item(row, 0)
            if status_item:
                icon = status_item.text()
                if icon == "✓":
                    dep["status"] = "installed"
                elif icon == "✗":
                    dep["status"] = "missing"
                elif icon == "⚠":
                    dep["status"] = "warning"

            dependencies.append(dep)

        return {"dependencies": dependencies}

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        if "dependencies" in state:
            self.set_dependencies(state["dependencies"])
