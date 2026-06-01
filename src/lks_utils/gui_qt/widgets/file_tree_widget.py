"""
Qt tree widget for displaying file hierarchies.

Provides a reusable tree view component for showing files and folders
in an expandable tree structure, commonly used for file previews
in archive tools, backup tools, etc.
"""
from __future__ import annotations

import sys
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(
            None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QHBoxLayout,
)
from PySide6.QtGui import QIcon, QColor


class QFileTreeWidget(QWidget):
    """
    Tree widget for displaying file hierarchies.

    Features:
    - Hierarchical folder/file display
    - File count and size summaries
    - Expansion/collapse controls
    - Optional checkboxes for selection

    Signals:
        selection_changed: Emitted when file selection changes (if checkboxes enabled)
    """

    selection_changed = Signal(list)  # List of selected file paths

    def __init__(
        self,
        parent: QWidget | None = None,
        show_checkboxes: bool = False,
        show_size: bool = True,
        max_display_files: int = 1000,
    ) -> None:
        """Initialize the file tree widget.

        Args:
            parent: Parent widget
            show_checkboxes: Whether to show checkboxes for selection
            show_size: Whether to show file sizes in tree
            max_display_files: Maximum files to display before showing warning
        """
        super().__init__(parent)

        self.show_checkboxes = show_checkboxes
        self.show_size = show_size
        self.max_display_files = max_display_files

        self._tree: QTreeWidget | None = None
        self._summary_label: QLabel | None = None
        self._file_count: int = 0
        self._total_size: int = 0

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Summary label
        self._summary_label = QLabel("No files")
        self._summary_label.setStyleSheet("color: gray;")
        layout.addWidget(self._summary_label)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(
            ["Name", "Size"] if self.show_size else ["Name"])
        self._tree.setColumnWidth(0, 400)
        if self.show_size:
            self._tree.setColumnWidth(1, 100)
        self._tree.setAlternatingRowColors(True)

        if self.show_checkboxes:
            self._tree.itemChanged.connect(self._on_item_changed)

        layout.addWidget(self._tree)

        # Expand/collapse buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)

        from PySide6.QtWidgets import QPushButton
        expand_all_btn = QPushButton("Expand All")
        expand_all_btn.clicked.connect(self._tree.expandAll)
        button_layout.addWidget(expand_all_btn)

        collapse_all_btn = QPushButton("Collapse All")
        collapse_all_btn.clicked.connect(self._tree.collapseAll)
        button_layout.addWidget(collapse_all_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

    def set_files(self, root_path: Path, relative_paths: list[Path]) -> None:
        """Set the files to display in the tree.

        Args:
            root_path: Root directory for the files
            relative_paths: List of relative file paths
        """
        self._tree.clear()
        self._file_count = len(relative_paths)
        self._total_size = 0

        # Check if too many files
        if self._file_count > self.max_display_files:
            item = QTreeWidgetItem(self._tree)
            item.setText(
                0, f"⚠️ Too many files to display ({self._file_count} files)")
            item.setText(1, "Use filters to reduce file count")
            self._update_summary()
            return

        # Build tree structure
        folder_items: dict[Path, QTreeWidgetItem] = {}

        # Sort paths by depth and name
        sorted_paths = sorted(
            relative_paths, key=lambda p: (len(p.parts), str(p)))

        for rel_path in sorted_paths:
            full_path = root_path / rel_path

            # Calculate size if file exists
            size = 0
            if full_path.exists() and full_path.is_file():
                try:
                    size = full_path.stat().st_size
                    self._total_size += size
                except Exception:
                    pass

            # Get or create parent folder items
            parent_item = None
            if rel_path.parent != Path("."):
                parent_parts = rel_path.parent.parts
                for i in range(len(parent_parts)):
                    folder_path = Path(*parent_parts[:i+1])

                    if folder_path not in folder_items:
                        folder_name = parent_parts[i]

                        # Determine parent for this folder
                        if i == 0:
                            folder_item = QTreeWidgetItem(self._tree)
                        else:
                            parent_folder = Path(*parent_parts[:i])
                            folder_item = QTreeWidgetItem(
                                folder_items[parent_folder])

                        folder_item.setText(0, f"📁 {folder_name}")
                        if self.show_size:
                            folder_item.setText(1, "")

                        folder_items[folder_path] = folder_item

                    parent_item = folder_items[folder_path]

            # Create file item
            if parent_item is None:
                file_item = QTreeWidgetItem(self._tree)
            else:
                file_item = QTreeWidgetItem(parent_item)

            file_item.setText(0, f"📄 {rel_path.name}")
            if self.show_size:
                file_item.setText(1, self._format_size(size))

            if self.show_checkboxes:
                file_item.setFlags(file_item.flags() | Qt.ItemIsUserCheckable)
                file_item.setCheckState(0, Qt.Checked)

            # Store full path in item data
            file_item.setData(0, Qt.UserRole, str(rel_path))

        self._update_summary()

        # Expand top-level folders
        for i in range(min(5, self._tree.topLevelItemCount())):
            self._tree.topLevelItem(i).setExpanded(True)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle item check state change."""
        if self.show_checkboxes:
            selected = self.get_selected_files()
            self.selection_changed.emit(selected)

    def get_selected_files(self) -> list[Path]:
        """Get list of selected files (if checkboxes enabled).

        Returns:
            List of relative file paths that are checked
        """
        if not self.show_checkboxes:
            return []

        selected: list[Path] = []

        def check_item(item: QTreeWidgetItem) -> None:
            if item.checkState(0) == Qt.Checked:
                path_str = item.data(0, Qt.UserRole)
                if path_str:  # Only files have paths stored
                    selected.append(Path(path_str))

            for i in range(item.childCount()):
                check_item(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            check_item(self._tree.topLevelItem(i))

        return selected

    def _update_summary(self) -> None:
        """Update the summary label."""
        if self._file_count == 0:
            self._summary_label.setText("No files")
        elif self._file_count > self.max_display_files:
            self._summary_label.setText(
                f"⚠️ {self._file_count} files (too many to display)"
            )
        else:
            size_str = self._format_size(
                self._total_size) if self.show_size else ""
            if size_str:
                self._summary_label.setText(
                    f"📊 {self._file_count} files • {size_str}"
                )
            else:
                self._summary_label.setText(f"📊 {self._file_count} files")

    def _format_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def clear(self) -> None:
        """Clear the tree."""
        self._tree.clear()
        self._file_count = 0
        self._total_size = 0
        self._update_summary()

    def show_loading(self, message: str = "Loading...") -> None:
        """Show a loading message in the tree.

        Args:
            message: Loading message to display
        """
        self._tree.clear()
        item = QTreeWidgetItem(self._tree)
        item.setText(0, f"⏳ {message}")
        item.setForeground(0, QColor("gray"))
        self._summary_label.setText(message)

    def show_message(self, message: str, is_error: bool = False) -> None:
        """Show a message in the tree.

        Args:
            message: Message to display
            is_error: Whether this is an error message
        """
        self._tree.clear()
        item = QTreeWidgetItem(self._tree)
        icon = "❌" if is_error else "ℹ️"
        item.setText(0, f"{icon} {message}")
        if is_error:
            item.setForeground(0, QColor("red"))
        else:
            item.setForeground(0, QColor("gray"))
        self._summary_label.setText(message if not is_error else "Error")

    def to_dict(self) -> dict[str, Any]:
        """Serialize widget state to dictionary."""
        return {
            "expanded_items": self._get_expanded_paths(),
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore widget state from dictionary."""
        if "expanded_items" in state:
            self._set_expanded_paths(state["expanded_items"])

    def _get_expanded_paths(self) -> list[str]:
        """Get list of expanded folder paths."""
        expanded: list[str] = []

        def check_item(item: QTreeWidgetItem, path: str = "") -> None:
            item_text = item.text(0).replace("📁 ", "").replace("📄 ", "")
            current_path = f"{path}/{item_text}" if path else item_text

            if item.isExpanded():
                expanded.append(current_path)

            for i in range(item.childCount()):
                check_item(item.child(i), current_path)

        for i in range(self._tree.topLevelItemCount()):
            check_item(self._tree.topLevelItem(i))

        return expanded

    def _set_expanded_paths(self, paths: list[str]) -> None:
        """Restore expanded state for folder paths."""
        # This is a simplified implementation
        # A full implementation would need to match paths correctly
        pass
