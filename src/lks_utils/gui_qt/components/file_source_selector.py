"""
File Source Selector Component (PySide6)

Reusable widget for selecting files from either a folder or individual file picker.
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
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.file_source import FileSource, get_filetypes_tuple
from lks_utils.gui_qt.widgets.tooltip import add_tooltip


class QFileSourceSelectorComponent(QGroupBox):
    """
    Reusable widget for selecting files from either a folder or individual file picker.

    This widget provides:
    - A path/selection display (read-only entry)
    - "Folder..." button to select a directory
    - "Files..." button to select individual files
    - Recursive checkbox (auto-disabled in file mode)
    - Callbacks for selection changes

    Signals:
        source_changed: Emitted when selection changes, passes FileSource

    Usage:
        selector = QFileSourceSelectorComponent(
            parent,
            title="Video Selection",
            extensions={'.mp4', '.avi', '.mkv'},
            file_type_name="Video files",
        )
        selector.source_changed.connect(lambda source: print(f"Selected: {source.display_text}"))

        # Later, get the selection:
        source = selector.get_source()
        if source.is_valid:
            files = find_files_by_extensions(source, VIDEO_EXTENSIONS)

    State persistence:
        state = selector.to_dict()
        selector.from_dict(state)
    """

    source_changed = Signal(object)  # FileSource

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "File Selection",
        extensions: set[str] | None = None,
        file_type_name: str = "Files",
        on_change: Callable[[FileSource], None] | None = None,
        show_recursive: bool = True,
        default_recursive: bool = True,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the QFileSourceSelectorComponent widget.

        Args:
            parent: Parent widget
            title: Title for the group box
            extensions: Set of file extensions to filter (e.g., {'.mp4', '.avi'})
            file_type_name: Description for file type in dialogs (e.g., "Video files")
            on_change: Callback when selection changes, receives FileSource
            show_recursive: Whether to show the recursive checkbox
            default_recursive: Default value for recursive checkbox
            **kwargs: Additional arguments passed to QGroupBox
        """
        super().__init__(title, parent, **kwargs)

        self.extensions: set[str] = extensions or set()
        self.file_type_name: str = file_type_name
        self._on_change_callback: Callable[[
            FileSource], None] | None = on_change
        self.show_recursive: bool = show_recursive

        # Internal state
        self._source: FileSource = FileSource(recursive=default_recursive)

        # Connect signal to callback if provided
        if self._on_change_callback:
            self.source_changed.connect(self._on_change_callback)

        # Build UI
        self._build_ui(default_recursive)

    def _build_ui(self, default_recursive: bool) -> None:
        """Build the widget UI."""
        layout = QGridLayout(self)
        layout.setSpacing(5)
        layout.setColumnStretch(1, 1)

        # Row 0: Source label and entry
        label = QLabel("Source:")
        layout.addWidget(label, 0, 0, Qt.AlignmentFlag.AlignLeft)

        self._path_entry = QLineEdit()
        self._path_entry.setReadOnly(False)
        self._path_entry.editingFinished.connect(self._on_path_edited)
        self._path_entry.returnPressed.connect(self._on_path_edited)
        layout.addWidget(self._path_entry, 0, 1)
        add_tooltip(self._path_entry, "Paste or type a folder/file path here")

        # Button frame
        btn_frame = QFrame()
        btn_layout = QHBoxLayout(btn_frame)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(3)

        self._folder_btn = QPushButton("Folder...")
        self._folder_btn.setFixedWidth(80)
        self._folder_btn.clicked.connect(self._browse_folder)
        btn_layout.addWidget(self._folder_btn)
        add_tooltip(self._folder_btn, "Select a folder to scan for files")

        self._files_btn = QPushButton("Files...")
        self._files_btn.setFixedWidth(80)
        self._files_btn.clicked.connect(self._browse_files)
        btn_layout.addWidget(self._files_btn)
        add_tooltip(self._files_btn, "Select individual files")

        layout.addWidget(btn_frame, 0, 2)

        # Row 1: Recursive checkbox (optional)
        if self.show_recursive:
            self._recursive_check = QCheckBox(
                "Search subdirectories recursively")
            self._recursive_check.setChecked(default_recursive)
            self._recursive_check.stateChanged.connect(
                self._on_recursive_changed)
            layout.addWidget(self._recursive_check, 1, 0, 1,
                             3, Qt.AlignmentFlag.AlignLeft)
            add_tooltip(
                self._recursive_check,
                "Search all subdirectories for files (only applies to folder selection)"
            )
        else:
            self._recursive_check = None

    def _browse_folder(self) -> None:
        """Handle folder browse button click."""
        path = QFileDialog.getExistingDirectory(
            self,
            f"Select {self.file_type_name} Folder"
        )
        if path:
            self._source.set_folder(path)
            self._source.recursive = self._recursive_check.isChecked(
            ) if self._recursive_check else True
            self._update_display()
            if self._recursive_check:
                self._recursive_check.setEnabled(True)
            self._notify_change()

    def _browse_files(self) -> None:
        """Handle files browse button click."""
        # Build filter string for Qt
        if self.extensions:
            tk_filetypes = get_filetypes_tuple(
                self.extensions, self.file_type_name)
            # Convert tkinter format to Qt format
            filter_parts: list[str] = []
            for desc, pattern in tk_filetypes:
                filter_parts.append(f"{desc} ({pattern})")
            filter_str = ";;".join(filter_parts)
        else:
            filter_str = "All files (*.*)"

        files, _ = QFileDialog.getOpenFileNames(
            self,
            f"Select {self.file_type_name}",
            "",
            filter_str
        )
        if files:
            self._source.set_files(files)
            self._update_display()
            if self._recursive_check:
                self._recursive_check.setEnabled(False)
            self._notify_change()

    def _on_path_edited(self) -> None:
        """Handle manual path entry or paste."""
        path_text = self._path_entry.text().strip()
        if not path_text:
            return

        path = Path(path_text)
        if path.is_dir():
            # User entered a folder path
            self._source.set_folder(str(path))
            self._source.recursive = self._recursive_check.isChecked(
            ) if self._recursive_check else True
            if self._recursive_check:
                self._recursive_check.setEnabled(True)
            self._update_display()
            self._notify_change()
        elif path.is_file():
            # User entered a single file path
            self._source.set_files([str(path)])
            if self._recursive_check:
                self._recursive_check.setEnabled(False)
            self._update_display()
            self._notify_change()
        else:
            # Invalid path - reset to previous value
            self._update_display()

    def _on_recursive_changed(self, state: int) -> None:
        """Handle recursive checkbox change."""
        self._source.recursive = self._recursive_check.isChecked(
        ) if self._recursive_check else True
        self._notify_change()

    def _update_display(self) -> None:
        """Update the path display."""
        self._path_entry.setText(self._source.display_text)

    def _notify_change(self) -> None:
        """Notify listener of selection change."""
        self.source_changed.emit(self._source)

    # ---- Public API ----

    def get_source(self) -> FileSource:
        """
        Get the current file source selection.

        Returns:
            FileSource with current selection
        """
        # Ensure recursive is up to date
        if self._recursive_check:
            self._source.recursive = self._recursive_check.isChecked()
        return self._source

    def set_folder(self, path: str | Path) -> None:
        """
        Programmatically set a folder selection.

        Args:
            path: Folder path to set
        """
        self._source.set_folder(path)
        self._update_display()
        if self._recursive_check:
            self._recursive_check.setEnabled(True)
        self._notify_change()

    def set_files(self, files: list[str | Path]) -> None:
        """
        Programmatically set file selections.

        Args:
            files: List of file paths
        """
        self._source.set_files(files)
        self._update_display()
        if self._recursive_check:
            self._recursive_check.setEnabled(False)
        self._notify_change()

    def clear(self) -> None:
        """Clear the current selection."""
        self._source.clear()
        self._path_entry.setText("")
        if self._recursive_check:
            self._recursive_check.setEnabled(True)
        self._notify_change()

    def set_recursive(self, recursive: bool) -> None:
        """Set the recursive checkbox state.

        Args:
            recursive: Whether to enable recursive search
        """
        if self._recursive_check:
            self._recursive_check.setChecked(recursive)
            self._source.recursive = recursive

    @property
    def is_valid(self) -> bool:
        """Check if current selection is valid."""
        return self._source.is_valid

    @property
    def is_folder_mode(self) -> bool:
        """Check if in folder mode."""
        return self._source.is_folder_mode

    @property
    def is_files_mode(self) -> bool:
        """Check if in files mode."""
        return self._source.is_files_mode

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: Whether component should be enabled.
        """
        self._folder_btn.setEnabled(enabled)
        self._files_btn.setEnabled(enabled)
        if self._recursive_check:
            self._recursive_check.setEnabled(enabled)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with source state.
        """
        source = self.get_source()
        return source.to_dict()

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with source state.
        """
        source = FileSource.from_dict(data)

        if source.is_folder_mode and source.folder_path:
            self.set_folder(source.folder_path)
        elif source.is_files_mode:
            self.set_files(source.files)
        else:
            self.clear()

        if self._recursive_check:
            self._recursive_check.setChecked(source.recursive)
        self._source.recursive = source.recursive
