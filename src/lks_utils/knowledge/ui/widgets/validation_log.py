"""Validation log widget for displaying graph validation errors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
)

from lks_utils.knowledge.default_theme import (
    SCENE_BACKGROUND_COLOR,
)


@dataclass(frozen=True)
class ValidationErrorEntry:
    """Single validation error entry."""

    node_id: str
    node_name: str
    field_name: str
    error_message: str
    error_level: str  # "error", "warning", "info"


class QKnowledgeValidationLogWidget(QWidget):
    """Widget displaying all validation errors in the graph.

    Shows a scrollable list of validation errors across all visible nodes,
    with node name, field, and error message. Clicking an entry can trigger
    focus/highlight of the problem node.
    """

    # Signal emitted when user clicks on a validation entry to focus that node
    focus_node_requested = Signal(str)  # node_id
    panel_height_changed = Signal(int)  # preferred panel height in px

    _COLLAPSED_PANEL_HEIGHT = 56
    _EXPANDED_MIN_HEIGHT = 88
    _EXPANDED_MAX_HEIGHT = 280
    _HEADER_HEIGHT = 24
    _ROW_HEIGHT = 24
    _VERTICAL_PADDING = 12

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize validation log widget.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._entries: list[ValidationErrorEntry] = []
        self._on_entry_click: Callable[[str], None] | None = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI layout."""
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Header label
        self._header = QLabel("Validation Issues")
        header_font = self._header.font()
        header_font.setBold(True)
        header_font.setPointSize(9)
        self._header.setFont(header_font)
        layout.addWidget(self._header)

        # Error list
        self._list_widget = QListWidget()
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._list_widget.setMaximumHeight(200)
        self._list_widget.setStyleSheet(
            """
            QListWidget {
                border: 1px solid #333333;
                border-radius: 2px;
            }
            QListWidget::item {
                min-height: 22px;
                padding: 3px 4px;
            }
            """
        )
        layout.addWidget(self._list_widget)

        self.setLayout(layout)
        self._apply_panel_height_policy(entry_count=0)

    def set_validation_errors(self, entries: list[ValidationErrorEntry]) -> None:
        """Update validation error log with new entries.

        Args:
            entries: List of validation error entries to display.
        """
        self._entries = entries
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the error list widget from current entries."""
        self._list_widget.clear()

        if not self._entries:
            empty_item = QListWidgetItem("✓ No validation issues")
            empty_item.setFlags(empty_item.flags() & ~
                                Qt.ItemFlag.ItemIsSelectable)
            empty_item.setSizeHint(QSize(0, 24))
            self._list_widget.addItem(empty_item)
            self._apply_panel_height_policy(entry_count=0)
            return

        for entry in self._entries:
            # Format: "NodeName.field: error message" with level badge
            level_icon = self._level_icon(entry.error_level)
            text = f"{level_icon} {entry.node_name}.{entry.field_name}: {entry.error_message}"

            item = QListWidgetItem(text)
            # Store node_id for click handling
            item.setData(Qt.ItemDataRole.UserRole, entry.node_id)

            # Color based on error level
            if entry.error_level == "error":
                item.setForeground(QColor("#ef4444"))  # Red
            elif entry.error_level == "warning":
                item.setForeground(QColor("#f59e0b"))  # Amber
            else:
                item.setForeground(QColor("#3b82f6"))  # Blue
            item.setSizeHint(QSize(0, self._ROW_HEIGHT))

            self._list_widget.addItem(item)
        self._apply_panel_height_policy(entry_count=len(self._entries))

    def preferred_panel_height(self) -> int:
        """Return preferred panel height for embedding splitters."""
        if not self._entries:
            return self._COLLAPSED_PANEL_HEIGHT
        rows = max(1, len(self._entries))
        list_height = min(
            rows * self._ROW_HEIGHT,
            self._EXPANDED_MAX_HEIGHT - self._HEADER_HEIGHT - self._VERTICAL_PADDING,
        )
        preferred = self._HEADER_HEIGHT + list_height + self._VERTICAL_PADDING
        return max(self._EXPANDED_MIN_HEIGHT, min(preferred, self._EXPANDED_MAX_HEIGHT))

    def _apply_panel_height_policy(self, *, entry_count: int) -> None:
        preferred = self.preferred_panel_height()
        if entry_count == 0:
            self._header.setText("Validation Issues")
            self._list_widget.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            self._list_widget.setMaximumHeight(26)
            self.setMinimumHeight(self._COLLAPSED_PANEL_HEIGHT)
            self.setMaximumHeight(self._COLLAPSED_PANEL_HEIGHT)
        else:
            self._header.setText(f"Validation Issues ({entry_count})")
            self._list_widget.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            self._list_widget.setMaximumHeight(
                max(40, preferred - self._HEADER_HEIGHT - self._VERTICAL_PADDING)
            )
            self.setMinimumHeight(min(self._EXPANDED_MIN_HEIGHT, preferred))
            self.setMaximumHeight(self._EXPANDED_MAX_HEIGHT)
        self.updateGeometry()
        self.panel_height_changed.emit(preferred)

    def _level_icon(self, level: str) -> str:
        """Get emoji/text icon for error level.

        Args:
            level: Error level ("error", "warning", "info").

        Returns:
            Icon string to display.
        """
        icons = {"error": "●", "warning": "⚠", "info": "ⓘ"}
        return icons.get(level, "●")

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """Handle validation entry click.

        Args:
            item: Clicked list item.
        """
        node_id = item.data(Qt.ItemDataRole.UserRole)
        if node_id:
            self.focus_node_requested.emit(node_id)
            if self._on_entry_click:
                self._on_entry_click(node_id)

    def set_on_entry_click(self, callback: Callable[[str], None]) -> None:
        """Set callback for when validation entry is clicked.

        Args:
            callback: Function that takes node_id as argument.
        """
        self._on_entry_click = callback

    def sizeHint(self) -> QSize:
        """Suggest compact size."""
        return QSize(220, self.preferred_panel_height())

    def get_error_count(self) -> int:
        """Get total number of validation errors.

        Returns:
            Count of errors.
        """
        return len([e for e in self._entries if e.error_level == "error"])

    def get_warning_count(self) -> int:
        """Get total number of warnings.

        Returns:
            Count of warnings.
        """
        return len([e for e in self._entries if e.error_level == "warning"])
