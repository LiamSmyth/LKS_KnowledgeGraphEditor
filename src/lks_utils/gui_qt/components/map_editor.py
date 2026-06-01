"""Enhanced map editor component with import/export and search functionality."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.library_component import QLibraryComponent
from lks_utils.gui_qt.components.mapping_editor import QMappingEditorComponent
from lks_utils.gui_qt.theme import COLORS


class QMapEditorComponent(QWidget):
    """Enhanced key-value map editor with library support and search.

    Features:
    - All features from QMappingEditorComponent (add/update/remove)
    - Save/Load/Store/Library toolbar (QLibraryComponent)
    - Optional custom library path for domain-specific presets
    - Search/filter by key or value
    - Duplicate key warning
    - Used for: symbol maps, activity maps, description maps, any lookup table

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
        height: int = 300,
        library_dir: str | None = None,
        value_options: list[str] | None = None,
    ) -> None:
        """Initialize enhanced map editor.

        Args:
            parent: Parent widget
            key_label: Label for key column
            value_label: Label for value column
            key_editable: Whether keys can be edited
            height: Minimum height of table in pixels
            library_dir: Optional custom library subdirectory (e.g., "stock_maps")
            value_options: Optional list of valid values for dropdown selection (enables enum mode)
        """
        super().__init__(parent)

        self._key_label = key_label
        self._value_label = value_label
        self._key_editable = key_editable
        self._height = height
        self._library_dir = library_dir
        self._value_options = value_options

        # State
        self._search_text = ""
        self._current_file: Path | None = None

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # --- Search Bar ---
        search_frame = QWidget()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(0, 0, 0, 0)

        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)

        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText("Filter by key or value...")
        self._search_entry.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_entry, stretch=1)

        self._search_clear_btn = QPushButton("Clear")
        self._search_clear_btn.clicked.connect(self._clear_search)
        search_layout.addWidget(self._search_clear_btn)

        layout.addWidget(search_frame)

        # --- Map Editor Component ---
        self._editor = QMappingEditorComponent(
            parent=self,
            key_label=self._key_label,
            value_label=self._value_label,
            key_editable=self._key_editable,
            show_buttons=True,
            height=self._height,
            value_options=self._value_options,
        )
        # Forward signals
        self._editor.mapping_changed.connect(self._on_mapping_changed)
        layout.addWidget(self._editor, stretch=1)

        # --- Library Component ---
        self._library = QLibraryComponent(
            parent=self,
            file_extension=".json",
            library_dir=self._library_dir,
        )
        # Connect signals
        self._library.data_requested.connect(self._on_data_requested)
        self._library.data_loaded.connect(self._on_data_loaded)
        layout.addWidget(self._library)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self._search_text = text.lower().strip()
        self._apply_filter()

    def _clear_search(self) -> None:
        """Clear search filter."""
        self._search_entry.clear()

    def _apply_filter(self) -> None:
        """Apply search filter to table."""
        if not self._search_text:
            # Show all rows
            for row in range(self._editor._table.rowCount()):
                self._editor._table.setRowHidden(row, False)
            return

        # Filter rows
        for row in range(self._editor._table.rowCount()):
            key_item = self._editor._table.item(row, 0)
            value_item = self._editor._table.item(row, 1)

            if key_item and value_item:
                key = key_item.text().lower()
                value = value_item.text().lower()
                matches = self._search_text in key or self._search_text in value
                self._editor._table.setRowHidden(row, not matches)

    def _on_mapping_changed(self, mappings: dict[str, str]) -> None:
        """Handle mapping change from inner editor."""
        self._apply_filter()
        self._library.mark_dirty()
        self.mapping_changed.emit(mappings)

    def _on_data_requested(self) -> None:
        """Called when library wants to save current data."""
        mappings = self._editor.get_mappings()
        data = json.dumps(mappings, indent=2, ensure_ascii=False)
        self._library.set_data(data)

    def _on_data_loaded(self, data: str) -> None:
        """Called when library has loaded data from file.

        Args:
            data: JSON string loaded from file
        """
        try:
            mappings = json.loads(data)

            # Validate data is a dict
            if not isinstance(mappings, dict):
                QMessageBox.critical(
                    self,
                    "Load Error",
                    "JSON file must contain a dictionary of key-value pairs.",
                )
                return

            # Check for duplicate keys
            current = self._editor.get_mappings()
            duplicates = [k for k in mappings if k in current]

            if duplicates and current:
                response = QMessageBox.question(
                    self,
                    "Duplicate Keys",
                    f"Found {len(duplicates)} duplicate key(s). Merge with existing?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if response == QMessageBox.Yes:
                    # Merge
                    new_mappings = current.copy()
                    new_mappings.update({str(k): str(v)
                                        for k, v in mappings.items()})
                    self._editor.set_mappings(new_mappings)
                else:
                    # Replace
                    self._editor.set_mappings(
                        {str(k): str(v) for k, v in mappings.items()})
            else:
                self._editor.set_mappings(
                    {str(k): str(v) for k, v in mappings.items()})

            self._library.mark_clean()

        except json.JSONDecodeError as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to parse JSON file:\\n{e}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load mappings:\\n{e}",
            )

    # --- Public API (delegates to inner editor) ---

    def set_mappings(self, mappings: dict[str, str]) -> None:
        """Set all mappings.

        Args:
            mappings: Dictionary of key-value pairs
        """
        self._editor.set_mappings(mappings)
        self._apply_filter()

    def get_mappings(self) -> dict[str, str]:
        """Get all mappings.

        Returns:
            Dictionary of key-value pairs
        """
        return self._editor.get_mappings()

    def add_mapping(self, key: str, value: str) -> None:
        """Add or update a single mapping programmatically.

        Args:
            key: Mapping key
            value: Mapping value
        """
        self._editor.add_mapping(key, value)

    def remove_mapping(self, key: str) -> None:
        """Remove a mapping by key.

        Args:
            key: Mapping key to remove
        """
        self._editor.remove_mapping(key)

    def has_mapping(self, key: str) -> bool:
        """Check if a mapping exists.

        Args:
            key: Mapping key to check

        Returns:
            True if mapping exists
        """
        return self._editor.has_mapping(key)

    def get_mapping(self, key: str, default: str = "") -> str:
        """Get value for a key.

        Args:
            key: Mapping key
            default: Default value if key not found

        Returns:
            Mapping value or default
        """
        return self._editor.get_mapping(key, default)

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        return {
            "mappings": self._editor.get_mappings(),
            "search_text": self._search_text,
        }

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        if "mappings" in state:
            self._editor.set_mappings(state["mappings"])
        if "search_text" in state:
            self._search_entry.setText(state["search_text"])


__all__ = ["QMapEditorComponent"]
