"""Path selector component with browse button (PySide6).

A reusable UI component for selecting file or folder paths.
Combines a QLineEdit widget with a Browse button, supporting:
- Single file selection
- Folder selection
- Optional file type filtering

Example:
    from lks_utils.gui_qt.components import QPathSelectorComponent
    
    # File selector
    file_selector = QPathSelectorComponent(
        parent,
        label="Input File:",
        mode="file",
        filetypes=[("Video files", "*.mp4 *.avi *.mkv")],
        on_change=lambda path: print(f"Selected: {path}")
    )
    
    # Folder selector
    folder_selector = QPathSelectorComponent(
        parent,
        label="Output Folder:",
        mode="folder",
    )
    
    # Get/set path
    path = file_selector.get_path()
    file_selector.set_path("C:/Videos/input.mp4")
    
    # State persistence
    state = file_selector.to_dict()
    file_selector.from_dict(state)
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


from pathlib import Path
from typing import Any, Callable, Literal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)
from PySide6.QtWidgets import QFileDialog as QFileDialogClass
from lks_utils.gui_qt.theme import DARK_QSS


class QPathSelectorComponent(QWidget):
    """Path selector with entry and browse button.

    Provides a consistent UI pattern for path selection across GUIs.

    Signals:
        path_changed: Emitted when path changes with new path string
    """

    path_changed = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "Path:",
        mode: Literal["file", "folder", "savefile"] = "file",
        filetypes: list[tuple[str, str]] | None = None,
        initial_dir: str | Path | None = None,
        placeholder: str = "",
        tooltip: str = "",
        on_change: Callable[[str], None] | None = None,
        entry_width: int = 40,
        button_text: str = "Browse...",
        button_width: int = 10,
        readonly: bool = True,
    ) -> None:
        """Initialize the path selector component.

        Args:
            parent: Parent widget
            label: Label text (empty string to hide label)
            mode: Selection mode - "file", "folder", or "savefile"
            filetypes: File type filters for file modes, e.g., [("Images", "*.jpg *.png")]
            initial_dir: Initial directory for file dialogs
            placeholder: Placeholder text when empty
            tooltip: Tooltip text for the entry widget
            on_change: Callback when path changes, receives new path
            entry_width: Width of entry widget in characters
            button_text: Text for browse button
            button_width: Width of browse button in characters
            readonly: If True, entry is read-only (only settable via browse/set_path)
        """
        super().__init__(parent)

        self.mode = mode
        self.filetypes = filetypes or [("All files", "*.*")]
        self.initial_dir = str(initial_dir) if initial_dir else None
        self.placeholder = placeholder
        self.on_change = on_change
        self.readonly = readonly

        self._build_ui(label, tooltip, entry_width, button_text, button_width)

        # Connect change handler
        if on_change:
            self.path_changed.connect(on_change)

    def _build_ui(
        self,
        label: str,
        tooltip: str,
        entry_width: int,
        button_text: str,
        button_width: int,
    ) -> None:
        """Build the component UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Label (optional)
        if label:
            self._label = QLabel(label)
            layout.addWidget(self._label)
        else:
            self._label = None

        # Entry
        self._entry = QLineEdit()
        self._entry.setReadOnly(self.readonly)
        self._entry.setPlaceholderText(self.placeholder)

        # Calculate width in pixels (rough approximation: 7px per char)
        entry_width_px: int = entry_width * 7
        self._entry.setMinimumWidth(entry_width_px)

        if tooltip:
            self._entry.setToolTip(tooltip)

        layout.addWidget(self._entry, stretch=1)

        # Browse button
        self._browse_btn = QPushButton(button_text)

        # Calculate button width in pixels
        button_width_px: int = button_width * 7
        self._browse_btn.setMinimumWidth(button_width_px)

        self._browse_btn.clicked.connect(self._browse)
        layout.addWidget(self._browse_btn)

        # Connect change handler for editable entries
        if not self.readonly:
            self._entry.textChanged.connect(self._on_text_changed)

    def _browse(self) -> None:
        """Handle browse button click using non-native, dark-friendly dialog."""
        initial: str = self.initial_dir or ""

        # Use current path's parent as initial dir if available
        current: str = self.get_path()
        if current and current != self.placeholder:
            current_path: Path = Path(current)
            if current_path.exists():
                initial = str(
                    current_path.parent if current_path.is_file() else current_path)

        result: str = ""

        if self.mode == "folder":
            dlg = QFileDialogClass(self, "Select Folder")
            dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dlg.setFileMode(QFileDialog.FileMode.Directory)
            dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
            if initial:
                dlg.setDirectory(initial)
            # Ensure readability on dark theme
            dlg.setStyleSheet(DARK_QSS + "\n QPushButton { color: white; }")
            if dlg.exec():
                selected = dlg.selectedFiles()
                result = selected[0] if selected else ""
        elif self.mode == "savefile":
            filter_str: str = self._build_filter_string()
            dlg = QFileDialogClass(self, "Save As")
            dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            dlg.setNameFilter(filter_str)
            if initial:
                dlg.setDirectory(initial)
            dlg.setStyleSheet(DARK_QSS + "\n QPushButton { color: white; }")
            if dlg.exec():
                selected = dlg.selectedFiles()
                result = selected[0] if selected else ""
        else:  # file
            filter_str: str = self._build_filter_string()
            dlg = QFileDialogClass(self, "Select File")
            dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dlg.setFileMode(QFileDialog.FileMode.ExistingFile)
            dlg.setNameFilter(filter_str)
            if initial:
                dlg.setDirectory(initial)
            dlg.setStyleSheet(DARK_QSS + "\n QPushButton { color: white; }")
            if dlg.exec():
                selected = dlg.selectedFiles()
                result = selected[0] if selected else ""

        if result:
            self.set_path(result)

    def _build_filter_string(self) -> str:
        """Build Qt file filter string from filetypes list.

        Converts [("Images", "*.jpg *.png")] to "Images (*.jpg *.png);;All files (*.*)"
        """
        filters: list[str] = []
        for name, extensions in self.filetypes:
            filters.append(f"{name} ({extensions})")
        return ";;".join(filters)

    def _on_text_changed(self, text: str) -> None:
        """Handle text change (for editable entries)."""
        path: str = self.get_path()
        self.path_changed.emit(path)

    def get_path(self) -> str:
        """Get the current path value.

        Returns:
            Current path string, or empty string if placeholder
        """
        value: str = self._entry.text()
        if value == self.placeholder or not value:
            return ""
        return value

    def set_path(self, path: str | Path) -> None:
        """Set the path value.

        Args:
            path: Path to set (empty string shows placeholder)
        """
        path_str: str = str(path) if path else ""
        self._entry.setText(path_str)

        # Emit signal
        self.path_changed.emit(self.get_path())

    def clear(self) -> None:
        """Clear the current path."""
        self.set_path("")

    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dict for persistence.

        Returns:
            Dictionary with path state
        """
        return {
            "path": self.get_path(),
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore component state from dict.

        Args:
            state: Dictionary with path state
        """
        if "path" in state:
            self.set_path(state["path"])

    @property
    def is_valid(self) -> bool:
        """Check if current path is valid (non-empty and exists for file/folder modes)."""
        path: str = self.get_path()
        if not path:
            return False

        path_obj: Path = Path(path)
        if self.mode == "savefile":
            # For save dialogs, parent must exist
            return path_obj.parent.exists()
        return path_obj.exists()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: True to enable, False to disable
        """
        self._entry.setEnabled(enabled)
        self._browse_btn.setEnabled(enabled)
