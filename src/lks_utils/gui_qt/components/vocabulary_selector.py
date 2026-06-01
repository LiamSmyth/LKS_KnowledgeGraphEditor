"""Vocabulary selector component for CLIP classification."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme import COLORS


class QVocabularySelectorComponent(QWidget):
    """Component for selecting vocabulary files for CLIP classification.

    Features:
    - Browse button to select vocabulary directory
    - Scrollable list of checkboxes for available vocabularies
    - Built-in vocabulary checkbox (always available)
    - Automatic scanning of directory for .txt/.csv files
    - Status indicator for directory selection
    - Info label showing selected count

    Signals:
    - vocab_dir_changed: Emitted when vocabulary directory changes
    - vocab_selection_changed: Emitted when any checkbox changes
    """

    vocab_dir_changed = Signal(str)  # directory path
    vocab_selection_changed = Signal(dict)  # {filename: bool}

    def __init__(
        self,
        parent: QWidget | None = None,
        show_browse_button: bool = True,
        show_builtin_checkbox: bool = True,
        builtin_label: str = "Built-in (~200 terms)",
        height: int = 160,
    ) -> None:
        """Initialize vocabulary selector.

        Args:
            parent: Parent widget
            show_browse_button: Show directory browse button
            show_builtin_checkbox: Show built-in vocabulary checkbox
            builtin_label: Label for built-in vocabulary
            height: Height of scrollable area in pixels
        """
        super().__init__(parent)

        self._show_browse = show_browse_button
        self._show_builtin = show_builtin_checkbox
        self._builtin_label = builtin_label
        self._height = height

        # State
        self._vocab_dir: Path | None = None
        self._vocab_checkboxes: dict[str, QCheckBox] = {}
        self._builtin_checkbox: QCheckBox | None = None

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # --- Directory Selection Row ---
        if self._show_browse:
            dir_row = QWidget()
            dir_layout = QHBoxLayout(dir_row)
            dir_layout.setContentsMargins(0, 0, 0, 0)

            lbl_dir = QLabel("Vocabulary Dir:")
            dir_layout.addWidget(lbl_dir)

            self._entry_dir = QLabel("")
            self._entry_dir.setStyleSheet(
                f"color: {COLORS['fg']}; background-color: {COLORS['input_bg']}; padding: 4px; border: 1px solid {COLORS['border']};")
            self._entry_dir.setMinimumWidth(200)
            dir_layout.addWidget(self._entry_dir, stretch=1)

            btn_browse = QPushButton("Browse")
            btn_browse.clicked.connect(self._browse_directory)
            dir_layout.addWidget(btn_browse)

            self._lbl_dir_status = QLabel("")
            self._lbl_dir_status.setMinimumWidth(20)
            dir_layout.addWidget(self._lbl_dir_status)

            layout.addWidget(dir_row)

        # --- Vocabulary Selection Label ---
        lbl_vocabs = QLabel("Vocabularies:")
        layout.addWidget(lbl_vocabs)

        # --- Scrollable Vocabulary List ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(self._height)
        scroll_area.setMaximumHeight(self._height)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.StyledPanel)

        self._vocab_container = QWidget()
        self._vocab_layout = QVBoxLayout(self._vocab_container)
        self._vocab_layout.setContentsMargins(5, 5, 5, 5)
        self._vocab_layout.setSpacing(5)
        self._vocab_layout.setAlignment(Qt.AlignTop)

        scroll_area.setWidget(self._vocab_container)
        layout.addWidget(scroll_area)

        # --- Built-in Vocabulary Checkbox ---
        if self._show_builtin:
            self._builtin_checkbox = QCheckBox("Built-in vocabulary")
            self._builtin_checkbox.setChecked(True)
            self._builtin_checkbox.toggled.connect(self._on_checkbox_changed)
            self._vocab_layout.addWidget(self._builtin_checkbox)

        # --- Info Label ---
        self._lbl_info = QLabel(
            "✓ Built-in (~200 terms)" if self._show_builtin else "")
        self._lbl_info.setStyleSheet(
            f"color: {COLORS['light']}; font-size: 10px;")
        layout.addWidget(self._lbl_info)

    def _browse_directory(self) -> None:
        """Open directory browser."""
        current_dir = str(self._vocab_dir) if self._vocab_dir else ""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Vocabulary Directory",
            current_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if directory:
            self.set_vocabulary_dir(directory)

    def set_vocabulary_dir(self, directory: str | Path) -> None:
        """Set the vocabulary directory and scan for files.

        Args:
            directory: Path to vocabulary directory
        """
        self._vocab_dir = Path(directory) if directory else None

        if self._show_browse:
            self._entry_dir.setText(
                str(self._vocab_dir) if self._vocab_dir else "")
            self._update_dir_status()

        self._scan_vocabulary_files()
        self.vocab_dir_changed.emit(
            str(self._vocab_dir) if self._vocab_dir else "")
        self._update_info_label()

    def _update_dir_status(self) -> None:
        """Update directory status indicator."""
        if not self._show_browse:
            return

        if not self._vocab_dir:
            self._lbl_dir_status.setText("")
        elif self._vocab_dir.exists() and self._vocab_dir.is_dir():
            self._lbl_dir_status.setText("✓")
            self._lbl_dir_status.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self._lbl_dir_status.setText("✗")
            self._lbl_dir_status.setStyleSheet(f"color: {COLORS['danger']};")

    def _scan_vocabulary_files(self) -> None:
        """Scan directory for vocabulary files and create checkboxes."""
        # Clear existing custom vocabulary checkboxes
        for checkbox in self._vocab_checkboxes.values():
            checkbox.deleteLater()
        self._vocab_checkboxes.clear()

        if not self._vocab_dir or not self._vocab_dir.exists():
            return

        # Find all .txt and .csv files
        vocab_files = []
        for ext in ["*.txt", "*.csv"]:
            vocab_files.extend(self._vocab_dir.glob(ext))

        vocab_files.sort(key=lambda p: p.name.lower())

        # Create checkboxes for each file
        for vocab_file in vocab_files:
            checkbox = QCheckBox(vocab_file.stem)
            checkbox.setChecked(False)
            checkbox.setToolTip(f"{vocab_file.name}")
            checkbox.toggled.connect(self._on_checkbox_changed)

            self._vocab_checkboxes[vocab_file.name] = checkbox
            self._vocab_layout.addWidget(checkbox)

    def _on_checkbox_changed(self) -> None:
        """Handle checkbox state change."""
        self._update_info_label()
        self.vocab_selection_changed.emit(self.get_selected_vocabularies())

    def _update_info_label(self) -> None:
        """Update info label with selection summary."""
        selected_count = sum(
            1 for cb in self._vocab_checkboxes.values() if cb.isChecked())

        parts = []
        if self._builtin_checkbox and self._builtin_checkbox.isChecked():
            parts.append(f"✓ {self._builtin_label}")
        if selected_count > 0:
            parts.append(f"{selected_count} custom")

        if parts:
            self._lbl_info.setText(" + ".join(parts))
        else:
            self._lbl_info.setText("No vocabularies selected")

    def get_vocabulary_dir(self) -> str:
        """Get current vocabulary directory path.

        Returns:
            Directory path as string, or empty string if not set
        """
        return str(self._vocab_dir) if self._vocab_dir else ""

    def get_selected_vocabularies(self) -> dict[str, bool]:
        """Get dictionary of vocabulary selections.

        Returns:
            Dict mapping filename to checked state
        """
        result = {}
        if self._builtin_checkbox:
            result["__builtin__"] = self._builtin_checkbox.isChecked()
        for filename, checkbox in self._vocab_checkboxes.items():
            result[filename] = checkbox.isChecked()
        return result

    def set_selected_vocabularies(self, selections: dict[str, bool]) -> None:
        """Set vocabulary selections.

        Args:
            selections: Dict mapping filename to checked state
        """
        if self._builtin_checkbox and "__builtin__" in selections:
            self._builtin_checkbox.setChecked(selections["__builtin__"])

        for filename, checked in selections.items():
            if filename == "__builtin__":
                continue
            if filename in self._vocab_checkboxes:
                self._vocab_checkboxes[filename].setChecked(checked)

        self._update_info_label()

    def get_builtin_enabled(self) -> bool:
        """Check if built-in vocabulary is enabled.

        Returns:
            True if built-in checkbox is checked
        """
        return self._builtin_checkbox.isChecked() if self._builtin_checkbox else False

    def set_builtin_enabled(self, enabled: bool) -> None:
        """Enable/disable built-in vocabulary.

        Args:
            enabled: Whether to enable built-in vocabulary
        """
        if self._builtin_checkbox:
            self._builtin_checkbox.setChecked(enabled)

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        return {
            "vocabulary_dir": self.get_vocabulary_dir(),
            "selected_vocabularies": self.get_selected_vocabularies(),
        }

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        if "vocabulary_dir" in state and state["vocabulary_dir"]:
            self.set_vocabulary_dir(state["vocabulary_dir"])

        if "selected_vocabularies" in state:
            self.set_selected_vocabularies(state["selected_vocabularies"])
