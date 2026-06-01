"""Output directory selector component (PySide6).

A specialized path selector for output directories with:
- Browse button for folder selection
- Optional "use source directory" checkbox
- Placeholder text when empty (indicating source dir will be used)

Example:
    from lks_utils.gui_qt.components import QOutputDirComponent
    
    output_selector = QOutputDirComponent(
        parent,
        label="Output Directory:",
        show_use_source=True,
        on_change=lambda path, use_source: print(f"Output: {path or 'source dir'}")
    )
    
    # Get output path (empty means use source)
    path = output_selector.get_path()
    use_source = output_selector.use_source
    
    # State persistence
    state = output_selector.to_dict()
    output_selector.from_dict(state)
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

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)
from PySide6.QtWidgets import QFileDialog as QFileDialogClass
from lks_utils.gui_qt.theme import DARK_QSS


class QOutputDirComponent(QWidget):
    """Output directory selector with optional "use source" option.

    Provides a consistent UI pattern for output directory selection.
    When path is empty and use_source is True, indicates output goes
    to source directory.

    Signals:
        output_changed: Emitted when output config changes with (path, use_source)
    """

    output_changed = Signal(str, bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "Output Directory:",
        placeholder: str = "(same as source)",
        tooltip: str = "Output directory. Leave empty to use source folder.",
        show_use_source: bool = False,
        use_source_text: str = "Use source directory",
        use_source_default: bool = True,
        on_change: Callable[[str, bool], None] | None = None,
        entry_width: int = 40,
        button_width: int = 10,
    ) -> None:
        """Initialize the output directory component.

        Args:
            parent: Parent widget
            label: Label text (empty string to hide label)
            placeholder: Placeholder text when empty
            tooltip: Tooltip text for the entry widget
            show_use_source: Whether to show the "use source" checkbox
            use_source_text: Text for the use source checkbox
            use_source_default: Default value for use source checkbox
            on_change: Callback when path changes, receives (path, use_source)
            entry_width: Width of entry widget in characters
            button_width: Width of browse button in characters
        """
        super().__init__(parent)

        self.placeholder = placeholder
        self.on_change = on_change
        self.show_use_source = show_use_source
        self._use_source = use_source_default if show_use_source else False

        self._build_ui(label, tooltip, entry_width,
                       button_width, use_source_text)

        # Connect change handler
        if on_change:
            self.output_changed.connect(on_change)

        if show_use_source:
            self._on_use_source_changed()

    def _build_ui(
        self,
        label: str,
        tooltip: str,
        entry_width: int,
        button_width: int,
        use_source_text: str,
    ) -> None:
        """Build the component UI."""
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        row: int = 0
        col: int = 0

        # Label (optional)
        if label:
            self._label = QLabel(label)
            layout.addWidget(self._label, row, col)
            col += 1
        else:
            self._label = None

        # Entry
        self._entry = QLineEdit()
        self._entry.setReadOnly(True)
        self._entry.setPlaceholderText(self.placeholder)

        # Calculate width in pixels (rough approximation: 7px per char)
        entry_width_px: int = entry_width * 7
        self._entry.setMinimumWidth(entry_width_px)

        if tooltip:
            self._entry.setToolTip(tooltip)

        layout.addWidget(self._entry, row, col)
        layout.setColumnStretch(col, 1)
        entry_col: int = col
        col += 1

        # Browse button
        self._browse_btn = QPushButton("Browse...")

        # Calculate button width in pixels
        button_width_px: int = button_width * 7
        self._browse_btn.setMinimumWidth(button_width_px)

        self._browse_btn.clicked.connect(self._browse)
        layout.addWidget(self._browse_btn, row, col)

        # Use source checkbox (optional, on row 1)
        if self.show_use_source:
            row += 1
            self._use_source_cb = QCheckBox(use_source_text)
            self._use_source_cb.setChecked(self._use_source)
            self._use_source_cb.stateChanged.connect(
                self._on_use_source_changed)
            self._use_source_cb.setToolTip(
                "When enabled, output files will be saved in the same directory as the source files"
            )
            layout.addWidget(self._use_source_cb, row, entry_col, 1, 2)
        else:
            self._use_source_cb = None

    def _browse(self) -> None:
        """Handle browse button click using non-native, dark-friendly dialog."""
        initial: str = ""

        # Use current path as initial dir if available
        current: str = self.get_path()
        if current:
            current_path: Path = Path(current)
            if current_path.exists():
                initial = str(current_path)

        dlg = QFileDialogClass(self, "Select Output Directory")
        dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dlg.setFileMode(QFileDialog.FileMode.Directory)
        dlg.setOption(QFileDialog.Option.ShowDirsOnly, True)
        if initial:
            dlg.setDirectory(initial)
        dlg.setStyleSheet(DARK_QSS + "\n QPushButton { color: white; }")

        if dlg.exec():
            selected = dlg.selectedFiles()
            result: str = selected[0] if selected else ""
            if result:
                self.set_path(result)
                # Uncheck "use source" when explicitly selecting a folder
                if self.show_use_source:
                    self._use_source = False
                    self._use_source_cb.setChecked(False)
                    self._on_use_source_changed()

    def _on_use_source_changed(self) -> None:
        """Handle use source checkbox change."""
        use_source: bool = self._use_source_cb.isChecked() if self.show_use_source else False
        self._use_source = use_source

        if use_source:
            # Clear path and show placeholder
            self._entry.setText("")
            self._entry.setEnabled(False)
            self._browse_btn.setEnabled(False)
        else:
            # Re-enable selection
            self._entry.setEnabled(True)
            self._browse_btn.setEnabled(True)

        self._notify_change()

    def _notify_change(self) -> None:
        """Notify listener of change."""
        self.output_changed.emit(self.get_path(), self.use_source)

    def get_path(self) -> str:
        """Get the current output path.

        Returns:
            Current path string, or empty string if using source/placeholder
        """
        value: str = self._entry.text()
        if value == self.placeholder or not value:
            return ""
        return value

    def set_path(self, path: str | Path) -> None:
        """Set the output path.

        Args:
            path: Path to set (empty string shows placeholder)
        """
        path_str: str = str(path) if path else ""
        self._entry.setText(path_str)
        self._notify_change()

    @property
    def use_source(self) -> bool:
        """Check if "use source directory" is enabled."""
        if self.show_use_source:
            return self._use_source
        # If no checkbox, empty path means use source
        return not self.get_path()

    @use_source.setter
    def use_source(self, value: bool) -> None:
        """Set the "use source directory" option."""
        self._use_source = value
        if self.show_use_source:
            self._use_source_cb.setChecked(value)
            self._on_use_source_changed()

    def clear(self) -> None:
        """Clear the current path (reset to use source)."""
        self.set_path("")
        if self.show_use_source:
            self._use_source = True
            self._use_source_cb.setChecked(True)
            self._on_use_source_changed()

    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dict for persistence.

        Returns:
            Dictionary with output dir state
        """
        return {
            "path": self.get_path(),
            "use_source": self.use_source,
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore component state from dict.

        Args:
            state: Dictionary with output dir state
        """
        if "path" in state:
            self.set_path(state["path"])
        if "use_source" in state and self.show_use_source:
            self._use_source = state["use_source"]
            self._use_source_cb.setChecked(self._use_source)
            self._on_use_source_changed()

    @property
    def is_valid(self) -> bool:
        """Check if current configuration is valid.

        Returns True if using source directory, or if custom path exists.
        """
        if self.use_source:
            return True
        path: str = self.get_path()
        return bool(path) and Path(path).exists()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: True to enable, False to disable
        """
        if enabled:
            # Restore appropriate state based on use_source
            if self.show_use_source and self._use_source:
                self._entry.setEnabled(False)
                self._browse_btn.setEnabled(False)
            else:
                self._entry.setEnabled(True)
                self._browse_btn.setEnabled(True)
            if self.show_use_source:
                self._use_source_cb.setEnabled(True)
        else:
            self._entry.setEnabled(False)
            self._browse_btn.setEnabled(False)
            if self.show_use_source:
                self._use_source_cb.setEnabled(False)
