"""Library component for Save/Load/Store file operations (PySide6).

A reusable toolbar widget providing Save/Save As/Load/Store/Library/Delete
operations for any editor working with file-based data assets.

The component handles file I/O workflow but delegates serialization/deserialization
to the host via callbacks. It manages:
- File path tracking and dirty state
- Library directory scanning (multi-path with core + extras)
- Dialog invocations
- Button state management

Multi-Path Library Resolution:
- Core library: Read-only bundled defaults (in lks_utils/<module>/data/)
- Extra libraries: User-created/project-specific assets (writable)
- Store writes to last extra dir (or core if no extras)
- Delete only works on extra library files (core protected)

Example:
    from lks_utils.gui_qt.components import QLibraryComponent
    
    # Core library: bundled defaults in lks_utils
    core_dir = Path(lks_utils.csv.__file__).parent / "canonicalize" / "data" / "rulesets"
    # User library: project-specific assets
    user_dir = Path(__file__).parent / "data" / "rulesets"
    
    library = QLibraryComponent(
        parent=self,
        library_dir=core_dir,
        extra_library_dirs=[user_dir],
        file_filter="Rulesets (*.json);;All Files (*)",
        file_extension=".json",
        label="Ruleset",
    )
    
    # Connect signals
    library.data_requested.connect(self._on_data_requested)
    library.data_loaded.connect(self._on_data_loaded)
    library.title_changed.connect(self._update_window_title)
    
    # Mark dirty on edits
    self._editor.textChanged.connect(lambda: library.mark_dirty())
    
    def _on_data_requested(self) -> None:
        '''Library needs serialized data for save/store.'''
        data = self._build_data_dict()
        library.set_data(json.dumps(data, indent=2))
    
    def _on_data_loaded(self, content: str) -> None:
        '''Library loaded data from file.'''
        data = json.loads(content)
        self._populate_ui_from_dict(data)
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(
            None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QToolButton,
    QWidget,
)
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtCore import QUrl

from lks_utils.core import atomic_write
from lks_utils.text import sanitize_filename


class QLibraryComponent(QWidget):
    """Reusable toolbar for Save/Load/Store/Library file operations.

    Provides a consistent UI pattern for managing file-based data assets
    across editors. Handles file I/O workflow while delegating serialization
    to the host via callbacks.

    Signals:
        data_requested: Host must call set_data() in response
        data_loaded: Emits file content as string after load
        dirty_changed: Emits when dirty state changes
        title_changed: Emits display title (filename + dirty marker)
    """

    data_requested = Signal()
    data_loaded = Signal(str)
    dirty_changed = Signal(bool)
    title_changed = Signal(str)
    new_requested = Signal()
    """Emitted after the user confirms clearing to a blank state.

    The host should respond by resetting its editor to an empty document.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        library_dir: Path | str | None = None,
        extra_library_dirs: list[Path | str] | None = None,
        file_filter: str = "JSON Files (*.json);;All Files (*)",
        file_extension: str = ".json",
        label: str = "",
    ) -> None:
        """Initialize the library component.

        Args:
            parent: Parent widget
            library_dir: Core library directory (bundled in lks_utils module)
            extra_library_dirs: Additional library dirs (user repo, project-specific)
            file_filter: Qt file dialog filter string
            file_extension: Default extension for Store operations (with dot)
            label: Optional label prefix shown before buttons
        """
        super().__init__(parent)

        # Convert paths
        self._library_dir = Path(
            library_dir) if library_dir else Path.cwd() / "library"
        self._extra_library_dirs = [Path(p)
                                    for p in (extra_library_dirs or [])]
        self._file_filter = file_filter
        self._file_extension = file_extension
        self._label_text = label

        # State
        self._current_file_path: Path | None = None
        self._is_library_file: bool = False
        self._is_dirty: bool = False
        self._pending_data: str | None = None
        self._custom_library_dir: Path | None = None

        # Build UI
        self._build_ui()
        self._update_button_states()
        self._update_title()

    @property
    def all_library_dirs(self) -> list[Path]:
        """All library directories in priority order (core first, then extras, then custom)."""
        dirs = [self._library_dir] + self._extra_library_dirs
        if self._custom_library_dir:
            dirs.append(self._custom_library_dir)
        return dirs

    @property
    def store_dir(self) -> Path:
        """The directory Store writes to. Custom dir > last extra > core library_dir."""
        if self._custom_library_dir:
            return self._custom_library_dir
        if self._extra_library_dirs:
            return self._extra_library_dirs[-1]
        return self._library_dir

    @property
    def current_file(self) -> Path | None:
        """Current file path, or None if untitled."""
        return self._current_file_path

    @property
    def is_dirty(self) -> bool:
        """Whether unsaved changes exist."""
        return self._is_dirty

    @property
    def is_library_file(self) -> bool:
        """Whether current file is from library."""
        return self._is_library_file

    @property
    def custom_library_dir(self) -> Path | None:
        """User-set custom library directory, or None if not set."""
        return self._custom_library_dir

    @custom_library_dir.setter
    def custom_library_dir(self, path: Path | None) -> None:
        """Set or clear the custom library directory.

        Args:
            path: Directory path, or None to clear
        """
        self._custom_library_dir = path
        self._populate_library_menu()

    def _build_ui(self) -> None:
        """Build the toolbar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Set minimum width to prevent button overlap
        self.setMinimumWidth(600)

        # Optional label
        if self._label_text:
            label = QLabel(self._label_text)
            label.setStyleSheet("font-weight: bold;")
            layout.addWidget(label)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setToolTip("Save to current file (Ctrl+S)")
        self._save_btn.setShortcut("Ctrl+S")
        self._save_btn.clicked.connect(self.save)
        layout.addWidget(self._save_btn)

        # Save As button
        self._save_as_btn = QPushButton("Save As")
        self._save_as_btn.setToolTip("Save to new file (Ctrl+Shift+S)")
        self._save_as_btn.setShortcut("Ctrl+Shift+S")
        self._save_as_btn.clicked.connect(self.save_as)
        layout.addWidget(self._save_as_btn)

        # Load button
        self._load_btn = QPushButton("Load")
        self._load_btn.setToolTip("Load from file (Ctrl+O)")
        self._load_btn.setShortcut("Ctrl+O")
        self._load_btn.clicked.connect(self.load)
        layout.addWidget(self._load_btn)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # Store button
        self._store_btn = QPushButton("Store")
        self._store_btn.setToolTip("Copy to library with new name")
        self._store_btn.clicked.connect(self.store)
        layout.addWidget(self._store_btn)

        # Library dropdown
        self._library_btn = QToolButton()
        self._library_btn.setText("Library")
        self._library_btn.setToolTip("Load from library")
        self._library_btn.setPopupMode(QToolButton.InstantPopup)
        self._library_menu = QMenu(self)
        self._library_btn.setMenu(self._library_menu)
        layout.addWidget(self._library_btn)

        # Spacer
        layout.addStretch()

        # Status label (filename + dirty marker)
        self._status_label = QLabel("Untitled")
        self._status_label.setStyleSheet("font-style: italic; color: #888;")
        layout.addWidget(self._status_label)

    def _update_button_states(self) -> None:
        """Update button enabled states based on current context."""
        has_file = self._current_file_path is not None
        self._save_btn.setEnabled(has_file and self._is_dirty)

    def _update_title(self) -> None:
        """Update status label and emit title_changed signal."""
        if self._current_file_path:
            title = self._current_file_path.name
        else:
            title = "Untitled"

        if self._is_dirty:
            title += " *"

        self._status_label.setText(title)
        self.title_changed.emit(title)

    def _populate_library_menu(self) -> None:
        """Rebuild library dropdown menu from all library directories."""
        self._library_menu.clear()

        # Scan all library directories
        entries: dict[str, tuple[Path, str]] = {}  # name -> (path, source)

        # Core library
        if self._library_dir.exists():
            for file_path in sorted(self._library_dir.glob(f"*{self._file_extension}")):
                entries[file_path.name] = (file_path, "core")

        # Extra libraries (later ones override earlier ones)
        for extra_dir in self._extra_library_dirs:
            if extra_dir.exists():
                for file_path in sorted(extra_dir.glob(f"*{self._file_extension}")):
                    entries[file_path.name] = (file_path, "user")

        # Custom library directory (user-set via UI)
        if self._custom_library_dir and self._custom_library_dir.exists():
            for file_path in sorted(self._custom_library_dir.glob(f"*{self._file_extension}")):
                entries[file_path.name] = (file_path, "custom")

        # Build menu
        if not entries:
            action = self._library_menu.addAction("(No library files)")
            action.setEnabled(False)
        else:
            # Group by source
            core_entries = [(name, path) for name, (path, src)
                            in sorted(entries.items()) if src == "core"]
            user_entries = [(name, path) for name, (path, src)
                            in sorted(entries.items()) if src in ("user", "custom")]

            if core_entries:
                for name, path in core_entries:
                    action = self._library_menu.addAction(name)
                    action.triggered.connect(
                        lambda checked, p=path: self._load_library_file(p))

            if core_entries and user_entries:
                self._library_menu.addSeparator()

            if user_entries:
                for name, path in user_entries:
                    action = self._library_menu.addAction(name)
                    action.triggered.connect(
                        lambda checked, p=path: self._load_library_file(p))

        # Bottom actions
        self._library_menu.addSeparator()

        # Delete action (only enabled if current file is from extra/custom library)
        delete_action = self._library_menu.addAction("Delete...")
        deletable_dirs = list(self._extra_library_dirs)
        if self._custom_library_dir:
            deletable_dirs.append(self._custom_library_dir)
        can_delete = (
            self._is_library_file
            and self._current_file_path is not None
            and any(
                self._current_file_path.parent == d
                for d in deletable_dirs
            )
        )
        delete_action.setEnabled(can_delete)
        delete_action.triggered.connect(self.delete_from_library)

        # Open folder action
        open_folder_action = self._library_menu.addAction("Open Folder")
        open_folder_action.triggered.connect(self._open_library_folder)

        self._library_menu.addSeparator()

        # Set / Clear custom library location
        if self._custom_library_dir:
            set_location_action = self._library_menu.addAction(
                f"Library: {self._custom_library_dir}")
            set_location_action.setEnabled(False)

            change_action = self._library_menu.addAction(
                "Change Library Location...")
            change_action.triggered.connect(self._set_custom_library_location)

            clear_action = self._library_menu.addAction(
                "Clear Custom Location")
            clear_action.triggered.connect(self._clear_custom_library_location)
        else:
            set_location_action = self._library_menu.addAction(
                "Set Library Location...")
            set_location_action.triggered.connect(
                self._set_custom_library_location)

    def _open_library_folder(self) -> None:
        """Open the store directory in file explorer."""
        folder = self.store_dir
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _set_custom_library_location(self) -> None:
        """Open a directory picker to set a custom library location."""
        initial_dir = str(
            self._custom_library_dir) if self._custom_library_dir else str(Path.cwd())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Set Library Location",
            initial_dir,
        )
        if not folder:
            return

        path = Path(folder)
        self._custom_library_dir = path
        self._populate_library_menu()

    def _clear_custom_library_location(self) -> None:
        """Remove the custom library location."""
        self._custom_library_dir = None
        self._populate_library_menu()

    def _check_unsaved_changes(self) -> bool:
        """Prompt user about unsaved changes. Returns True if should proceed."""
        if not self._is_dirty:
            return True

        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Do you want to discard them?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _load_library_file(self, path: Path) -> None:
        """Load a file from library."""
        if not self._check_unsaved_changes():
            return

        try:
            content = path.read_text(encoding="utf-8")
            self._current_file_path = path
            self._is_library_file = True
            self._is_dirty = False
            self.data_loaded.emit(content)
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(False)
        except Exception as e:
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to load file:\n{e}")

    def new(self) -> bool:
        """Clear to a blank untitled state.

        Prompts the user if there are unsaved changes.  Resets the file path
        and dirty state, then emits :attr:`new_requested` so the host can
        clear its editor contents.

        Returns:
            ``True`` if the new operation proceeded, ``False`` if the user
            chose to keep unsaved changes.
        """
        if not self._check_unsaved_changes():
            return False
        self._current_file_path = None
        self._is_library_file = False
        self._is_dirty = False
        self._update_button_states()
        self._update_title()
        self.dirty_changed.emit(False)
        self.new_requested.emit()
        return True

    def set_data(self, content: str) -> None:
        """Host provides serialized data when data_requested signal fires.

        Args:
            content: Serialized data as string
        """
        self._pending_data = content

    def mark_dirty(self) -> None:
        """Host calls this when user modifies data in the editor."""
        if not self._is_dirty:
            self._is_dirty = True
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(True)

    def mark_clean(self) -> None:
        """Host calls this after programmatic load (e.g., preset selection)."""
        if self._is_dirty:
            self._is_dirty = False
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(False)

    def save(self) -> bool:
        """Save to current file. Routes to save_as if no current file.

        Returns:
            True if save succeeded, False otherwise
        """
        if self._current_file_path is None:
            return self.save_as()

        # Request data from host
        self._pending_data = None
        self.data_requested.emit()

        if self._pending_data is None:
            QMessageBox.warning(self, "Save Error",
                                "No data provided by host.")
            return False

        try:
            atomic_write(self._current_file_path,
                         self._pending_data.encode("utf-8"))
            self._is_dirty = False
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(False)
            self._populate_library_menu()  # Refresh dropdown
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error",
                                 f"Failed to save file:\n{e}")
            return False

    def save_as(self) -> bool:
        """Save to new file via file dialog.

        Returns:
            True if save succeeded, False otherwise
        """
        # Request data from host
        self._pending_data = None
        self.data_requested.emit()

        if self._pending_data is None:
            QMessageBox.warning(self, "Save Error",
                                "No data provided by host.")
            return False

        # Open save dialog
        initial_dir = str(
            self._current_file_path.parent) if self._current_file_path else str(Path.cwd())
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As",
            initial_dir,
            self._file_filter,
        )

        if not file_path:
            return False

        path = Path(file_path)

        try:
            atomic_write(path, self._pending_data.encode("utf-8"))
            self._current_file_path = path
            self._is_library_file = False
            self._is_dirty = False
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(False)
            self._populate_library_menu()  # Refresh dropdown
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error",
                                 f"Failed to save file:\n{e}")
            return False

    def load(self) -> bool:
        """Load from file via file dialog.

        Returns:
            True if load succeeded, False otherwise
        """
        if not self._check_unsaved_changes():
            return False

        # Open load dialog
        initial_dir = str(
            self._current_file_path.parent) if self._current_file_path else str(Path.cwd())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load",
            initial_dir,
            self._file_filter,
        )

        if not file_path:
            return False

        path = Path(file_path)

        try:
            content = path.read_text(encoding="utf-8")
            self._current_file_path = path
            self._is_library_file = False
            self._is_dirty = False
            self.data_loaded.emit(content)
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Load Error",
                                 f"Failed to load file:\n{e}")
            return False

    def store(self) -> bool:
        """Copy current data to library with new name.

        Returns:
            True if store succeeded, False otherwise
        """
        # Request data from host
        self._pending_data = None
        self.data_requested.emit()

        if self._pending_data is None:
            QMessageBox.warning(self, "Store Error",
                                "No data provided by host.")
            return False

        # Prompt for name
        name, ok = QInputDialog.getText(
            self,
            "Store to Library",
            "Enter name:",
        )

        if not ok or not name:
            return False

        # Sanitize name
        safe_name = sanitize_filename(name)
        if not safe_name:
            QMessageBox.warning(self, "Invalid Name",
                                "Name contains only invalid characters.")
            return False

        # Add extension if missing
        if not safe_name.endswith(self._file_extension):
            safe_name += self._file_extension

        # Check if file exists
        target_path = self.store_dir / safe_name
        if target_path.exists():
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"'{safe_name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False

        # Write to library
        try:
            self.store_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(target_path, self._pending_data.encode("utf-8"))
            self._populate_library_menu()  # Refresh dropdown
            return True
        except Exception as e:
            QMessageBox.critical(self, "Store Error",
                                 f"Failed to store to library:\n{e}")
            return False

    def load_from_library(self, name: str) -> bool:
        """Load a library file by name.

        Args:
            name: Library file name (with extension)

        Returns:
            True if load succeeded, False otherwise
        """
        # Search all library directories
        for lib_dir in reversed(self.all_library_dirs):  # Prefer extras
            path = lib_dir / name
            if path.exists():
                if not self._check_unsaved_changes():
                    return False
                self._load_library_file(path)
                return True

        QMessageBox.warning(self, "Not Found",
                            f"'{name}' not found in library.")
        return False

    def delete_from_library(self) -> bool:
        """Delete current file from library (only works on extra library files).

        Returns:
            True if delete succeeded, False otherwise
        """
        if not self._is_library_file or self._current_file_path is None:
            QMessageBox.warning(self, "Delete Error",
                                "No library file to delete.")
            return False

        # Check if file is in an extra or custom library dir
        deletable_dirs = list(self._extra_library_dirs)
        if self._custom_library_dir:
            deletable_dirs.append(self._custom_library_dir)
        is_deletable = any(
            self._current_file_path.parent == d
            for d in deletable_dirs
        )

        if not is_deletable:
            QMessageBox.warning(
                self,
                "Cannot Delete",
                "Core library files cannot be deleted through the UI.",
            )
            return False

        # Confirm deletion
        reply = QMessageBox.question(
            self,
            "Delete from Library",
            f"Delete '{self._current_file_path.name}' from library?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return False

        # Delete file
        try:
            self._current_file_path.unlink()
            # Clear file path but keep data in editor
            self._current_file_path = None
            self._is_library_file = False
            self._is_dirty = True
            self._update_button_states()
            self._update_title()
            self.dirty_changed.emit(True)
            self._populate_library_menu()  # Refresh dropdown
            return True
        except Exception as e:
            QMessageBox.critical(self, "Delete Error",
                                 f"Failed to delete file:\n{e}")
            return False

    def list_library(self) -> list[str]:
        """List all library file names (merged from all library directories).

        Returns:
            List of file names (deduplicated, extras shadow core)
        """
        names: set[str] = set()
        for lib_dir in self.all_library_dirs:
            if lib_dir.exists():
                for path in lib_dir.glob(f"*{self._file_extension}"):
                    names.add(path.name)
        return sorted(names)

    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dictionary.

        Returns:
            Dictionary with keys: current_file, is_library_file, source_dir,
            custom_library_dir
        """
        source_dir = None
        if self._current_file_path:
            source_dir = str(self._current_file_path.parent)

        return {
            "current_file": str(self._current_file_path) if self._current_file_path else None,
            "is_library_file": self._is_library_file,
            "source_dir": source_dir,
            "custom_library_dir": str(self._custom_library_dir) if self._custom_library_dir else None,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore component state from dictionary.

        Does NOT reload file content — host handles that via data_loaded signal.

        Args:
            data: Dictionary from to_dict()
        """
        current_file = data.get("current_file")
        if current_file:
            path = Path(current_file)
            if path.exists():
                self._current_file_path = path
                self._is_library_file = data.get("is_library_file", False)
            else:
                # File no longer exists, clear to Untitled
                self._current_file_path = None
                self._is_library_file = False
        else:
            self._current_file_path = None
            self._is_library_file = False

        # Restore custom library location
        custom_dir = data.get("custom_library_dir")
        if custom_dir:
            custom_path = Path(custom_dir)
            if custom_path.is_dir():
                self._custom_library_dir = custom_path
            else:
                self._custom_library_dir = None
        else:
            self._custom_library_dir = None

        # Assume clean after restore (host must mark_dirty if needed)
        self._is_dirty = False
        self._update_button_states()
        self._update_title()

    def setEnabled(self, enabled: bool) -> None:
        """Enable/disable all buttons.

        Args:
            enabled: Whether to enable buttons
        """
        super().setEnabled(enabled)
        self._save_btn.setEnabled(
            enabled and self._current_file_path is not None and self._is_dirty)
        self._save_as_btn.setEnabled(enabled)
        self._load_btn.setEnabled(enabled)
        self._store_btn.setEnabled(enabled)
        self._library_btn.setEnabled(enabled)

    def showEvent(self, event) -> None:
        """Rebuild library menu when widget is shown."""
        super().showEvent(event)
        self._populate_library_menu()
