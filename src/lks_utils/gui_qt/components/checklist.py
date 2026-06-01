"""
QChecklistComponent - Manages a list of checkbox items.

Provides a clean interface for creating and managing multiple
checkbox items with consistent layout and state management.
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


from typing import Any, Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.checkbox_item import QCheckboxItemComponent


class QChecklistComponent(QWidget):
    """
    Container for managing multiple checkbox items.

    **Features**:
    - Add/remove checkbox items dynamically
    - Get all checked items
    - Bulk check/uncheck operations
    - State persistence for all items
    - Scrollable when many items

    **Interface**:
    - `add_item(label, ...) → QCheckboxItemComponent`
    - `remove_item(label)` → None
    - `get_item(label)` → QCheckboxItemComponent | None
    - `get_checked_labels()` → list[str]
    - `set_all_checked(checked)` → None
    - `clear()` → None
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None

    **Signals**:
    - `item_toggled(label: str, checked: bool)` - Emitted when any item toggles

    **Example**:
    ```python
    # Create checklist
    checklist = QChecklistComponent()

    # Add items
    checklist.add_item(
        label="Enable feature",
        description="Experimental feature",
        checked=True,
        on_toggle=lambda checked: print(f"Feature: {checked}")
    )

    # Get checked items
    checked = checklist.get_checked_labels()
    print(f"Checked: {checked}")

    # Check/uncheck all
    checklist.set_all_checked(True)
    ```
    """

    item_toggled = Signal(str, bool)  # label, checked

    def __init__(
        self,
        parent: QWidget | None = None,
        scrollable: bool = True,
    ) -> None:
        """
        Initialize checklist component.

        Args:
            parent: Parent widget.
            scrollable: Whether to make the list scrollable.
        """
        super().__init__(parent)

        self._items: dict[str, QCheckboxItemComponent] = {}
        self._scrollable = scrollable

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if self._scrollable:
            # Create scroll area
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)

            # Content widget for scroll area
            self._content_widget = QWidget()
            self._content_layout = QVBoxLayout(self._content_widget)
            self._content_layout.setContentsMargins(0, 0, 0, 0)
            self._content_layout.setSpacing(5)

            scroll.setWidget(self._content_widget)
            layout.addWidget(scroll)
        else:
            # Direct layout (no scrolling)
            self._content_widget = self
            self._content_layout = layout
            self._content_layout.setSpacing(5)

        # Add stretch at bottom to push items to top
        self._content_layout.addStretch()

    def add_item(
        self,
        label: str,
        description: str = "",
        checked: bool = False,
        status_text: str = "",
        status_color: str = "gray",
        on_toggle: Callable[[bool], None] | None = None,
    ) -> QCheckboxItemComponent:
        """
        Add a checkbox item to the list.

        Args:
            label: Primary label text.
            description: Optional description text.
            checked: Initial checked state.
            status_text: Optional status text.
            status_color: Color for status text.
            on_toggle: Callback when this item is toggled.

        Returns:
            The created QCheckboxItemComponent.

        Raises:
            ValueError: If an item with this label already exists.
        """
        if label in self._items:
            raise ValueError(f"Item with label '{label}' already exists")

        # Create item
        item = QCheckboxItemComponent(
            parent=self._content_widget,
            label=label,
            description=description,
            checked=checked,
            status_text=status_text,
            status_color=status_color,
        )

        # Connect toggle signal
        item.toggled.connect(
            lambda checked, lbl=label: self._on_item_toggled(lbl, checked)
        )

        # Store custom callback if provided
        if on_toggle:
            item.toggled.connect(on_toggle)

        # Add to layout (before stretch)
        count = self._content_layout.count()
        self._content_layout.insertWidget(count - 1, item)

        # Store reference
        self._items[label] = item

        return item

    def remove_item(self, label: str) -> None:
        """
        Remove a checkbox item from the list.

        Args:
            label: Label of the item to remove.

        Raises:
            KeyError: If item with this label doesn't exist.
        """
        if label not in self._items:
            raise KeyError(f"Item with label '{label}' not found")

        item = self._items[label]
        self._content_layout.removeWidget(item)
        item.deleteLater()
        del self._items[label]

    def get_item(self, label: str) -> QCheckboxItemComponent | None:
        """
        Get a checkbox item by label.

        Args:
            label: Label of the item.

        Returns:
            The QCheckboxItemComponent or None if not found.
        """
        return self._items.get(label)

    def get_all_labels(self) -> list[str]:
        """
        Get all item labels.

        Returns:
            List of all labels.
        """
        return list(self._items.keys())

    def get_checked_labels(self) -> list[str]:
        """
        Get labels of all checked items.

        Returns:
            List of labels for checked items.
        """
        return [
            label
            for label, item in self._items.items()
            if item.is_checked()
        ]

    def get_unchecked_labels(self) -> list[str]:
        """
        Get labels of all unchecked items.

        Returns:
            List of labels for unchecked items.
        """
        return [
            label
            for label, item in self._items.items()
            if not item.is_checked()
        ]

    def set_all_checked(self, checked: bool) -> None:
        """
        Check or uncheck all items.

        Args:
            checked: True to check all, False to uncheck all.
        """
        for item in self._items.values():
            if item.isEnabled():
                item.set_checked(checked)

    def clear(self) -> None:
        """Remove all items from the list."""
        for label in list(self._items.keys()):
            self.remove_item(label)

    def _on_item_toggled(self, label: str, checked: bool) -> None:
        """Handle item toggle."""
        self.item_toggled.emit(label, checked)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with all items' states.
        """
        return {
            "items": {
                label: item.to_dict()
                for label, item in self._items.items()
            }
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Note: This only updates existing items' states.
        It does not add/remove items.

        Args:
            data: Dict with items' states.
        """
        items_data = data.get("items", {})
        for label, item_data in items_data.items():
            item = self.get_item(label)
            if item:
                item.from_dict(item_data)

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable all items.

        Args:
            enabled: True to enable, False to disable.
        """
        for item in self._items.values():
            item.set_enabled(enabled)
