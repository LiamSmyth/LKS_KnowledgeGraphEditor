"""
Qt component for managing file pattern lists (include/exclude).

Provides:
- Checkboxes for bundled presets (IDE, Build Artifacts, etc.)
- Custom pattern list with add/remove/edit
- Pattern testing dialog
- Preset save/load functionality
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
    QHBoxLayout,
    QGroupBox,
    QCheckBox,
    QListWidget,
    QPushButton,
    QInputDialog,
    QMessageBox,
    QFileDialog,
    QDialog,
    QLabel,
    QTextEdit,
)

from lks_utils.path.pattern_presets import (
    PatternPreset,
    list_presets,
    load_preset,
    save_preset,
    export_preset,
    import_preset,
    get_combined_patterns,
)
from lks_utils.path import FileSet


class QPatternListComponent(QWidget):
    """
    Qt component for managing file pattern lists.

    Features:
    - Multi-select preset checkboxes
    - Custom pattern list with add/remove/edit
    - Test patterns against directory
    - Save/load presets

    Signals:
        patterns_changed: Emitted when pattern list changes
    """

    patterns_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._preset_checkboxes: dict[str, QCheckBox] = {}
        self._custom_patterns_list: QListWidget | None = None

        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Preset section
        preset_group = QGroupBox("Bundled Presets")
        preset_layout = QVBoxLayout(preset_group)

        presets: list[PatternPreset] = list_presets()
        for preset in presets:
            if preset.category == "builtin":
                checkbox = QCheckBox(preset.name)
                checkbox.setToolTip(preset.description)
                checkbox.stateChanged.connect(self._on_preset_changed)
                self._preset_checkboxes[preset.name] = checkbox
                preset_layout.addWidget(checkbox)

        layout.addWidget(preset_group)

        # Custom patterns section
        custom_group = QGroupBox("Custom Patterns")
        custom_layout = QVBoxLayout(custom_group)

        self._custom_patterns_list = QListWidget()
        self._custom_patterns_list.itemDoubleClicked.connect(
            self._on_edit_pattern)
        custom_layout.addWidget(self._custom_patterns_list)

        # Add/Remove buttons
        button_row = QHBoxLayout()
        add_btn = QPushButton("Add Pattern")
        add_btn.clicked.connect(self._on_add_pattern)
        button_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_pattern)
        button_row.addWidget(remove_btn)

        button_row.addStretch()
        custom_layout.addLayout(button_row)

        layout.addWidget(custom_group)

        # Action buttons
        action_row = QHBoxLayout()

        test_btn = QPushButton("Test Patterns...")
        test_btn.clicked.connect(self._on_test_patterns)
        action_row.addWidget(test_btn)

        save_preset_btn = QPushButton("Save as Preset...")
        save_preset_btn.clicked.connect(self._on_save_preset)
        action_row.addWidget(save_preset_btn)

        load_btn = QPushButton("Import...")
        load_btn.clicked.connect(self._on_import_preset)
        action_row.addWidget(load_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

    def _on_preset_changed(self) -> None:
        """Handle preset checkbox state change."""
        self.patterns_changed.emit()

    def _on_add_pattern(self) -> None:
        """Add a new custom pattern."""
        pattern, ok = QInputDialog.getText(
            self,
            "Add Pattern",
            "Enter pattern (e.g., *.pyc, __pycache__, .git):"
        )

        if ok and pattern:
            if self._custom_patterns_list is not None:
                self._custom_patterns_list.addItem(pattern.strip())
                self.patterns_changed.emit()

    def _on_remove_pattern(self) -> None:
        """Remove selected custom pattern."""
        if self._custom_patterns_list is None:
            return

        current_item = self._custom_patterns_list.currentItem()
        if current_item:
            row = self._custom_patterns_list.row(current_item)
            self._custom_patterns_list.takeItem(row)
            self.patterns_changed.emit()

    def _on_edit_pattern(self) -> None:
        """Edit pattern on double-click."""
        if self._custom_patterns_list is None:
            return

        current_item = self._custom_patterns_list.currentItem()
        if current_item:
            old_pattern = current_item.text()
            pattern, ok = QInputDialog.getText(
                self,
                "Edit Pattern",
                "Pattern:",
                text=old_pattern
            )

            if ok and pattern:
                current_item.setText(pattern.strip())
                self.patterns_changed.emit()

    def _on_test_patterns(self) -> None:
        """Open dialog to test patterns against a directory."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Test Patterns"
        )

        if not directory:
            return

        # Get all patterns
        all_patterns = self.get_patterns()
        if not all_patterns:
            QMessageBox.information(
                self,
                "No Patterns",
                "No patterns selected. Please check presets or add custom patterns."
            )
            return

        # Create test dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Pattern Test Results")
        dialog.resize(600, 400)

        layout = QVBoxLayout(dialog)

        # Info label
        info_label = QLabel(
            f"Testing {len(all_patterns)} patterns against:\n{directory}")
        layout.addWidget(info_label)

        # Results text
        results_text = QTextEdit()
        results_text.setReadOnly(True)

        try:
            # Load directory
            file_set = FileSet.from_directory(Path(directory), recursive=True)

            # Apply patterns
            filtered = file_set.apply_patterns(exclude_patterns=all_patterns)

            excluded_count = len(file_set.relative_paths) - \
                len(filtered.relative_paths)

            results = [
                f"Total files found: {len(file_set.relative_paths)}",
                f"Files after filtering: {len(filtered.relative_paths)}",
                f"Files excluded: {excluded_count}",
                "",
                "Excluded files:",
            ]

            excluded_files = set(file_set.relative_paths) - \
                set(filtered.relative_paths)
            for rel_path in sorted(excluded_files):
                results.append(f"  - {rel_path}")

            results_text.setPlainText("\n".join(results))

        except Exception as e:
            results_text.setPlainText(f"Error testing patterns: {e}")

        layout.addWidget(results_text)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def _on_save_preset(self) -> None:
        """Save current custom patterns as a preset."""
        if self._custom_patterns_list is None or self._custom_patterns_list.count() == 0:
            QMessageBox.warning(
                self,
                "No Patterns",
                "No custom patterns to save. Add patterns first."
            )
            return

        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Preset name:"
        )

        if not ok or not name:
            return

        description, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Description (optional):"
        )

        if not ok:
            return

        # Get custom patterns
        patterns: list[str] = []
        for i in range(self._custom_patterns_list.count()):
            item = self._custom_patterns_list.item(i)
            if item:
                patterns.append(item.text())

        # Create preset
        preset = PatternPreset(
            name=name.strip(),
            description=description.strip() if description else "",
            patterns=patterns,
            category="custom",
        )

        try:
            save_preset(preset, overwrite=False)
            QMessageBox.information(
                self,
                "Success",
                f"Preset '{name}' saved successfully."
            )
        except FileExistsError:
            reply = QMessageBox.question(
                self,
                "Preset Exists",
                f"Preset '{name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                save_preset(preset, overwrite=True)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Preset '{name}' updated successfully."
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save preset: {e}"
            )

    def _on_import_preset(self) -> None:
        """Import preset from JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Preset",
            "",
            "JSON Files (*.json)"
        )

        if not file_path:
            return

        try:
            preset = import_preset(Path(file_path))

            # Add patterns to custom list
            if self._custom_patterns_list is not None:
                for pattern in preset.patterns:
                    self._custom_patterns_list.addItem(pattern)

                self.patterns_changed.emit()

                QMessageBox.information(
                    self,
                    "Success",
                    f"Imported {len(preset.patterns)} patterns from '{preset.name}'."
                )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to import preset: {e}"
            )

    def get_patterns(self) -> list[str]:
        """
        Get all patterns (selected presets + custom patterns).

        Returns:
            Combined list of patterns, deduplicated
        """
        all_patterns: list[str] = []

        # Get selected preset names
        selected_presets: list[str] = []
        for name, checkbox in self._preset_checkboxes.items():
            if checkbox.isChecked():
                selected_presets.append(name)

        # Get combined patterns from presets
        if selected_presets:
            all_patterns.extend(get_combined_patterns(selected_presets))

        # Add custom patterns
        if self._custom_patterns_list is not None:
            for i in range(self._custom_patterns_list.count()):
                item = self._custom_patterns_list.item(i)
                if item:
                    pattern = item.text().strip()
                    if pattern and pattern not in all_patterns:
                        all_patterns.append(pattern)

        return all_patterns

    def set_patterns(
        self,
        preset_names: list[str] | None = None,
        custom_patterns: list[str] | None = None
    ) -> None:
        """
        Set patterns (presets and custom).

        Args:
            preset_names: Names of presets to check
            custom_patterns: Custom patterns to add
        """
        # Clear preset selections
        for checkbox in self._preset_checkboxes.values():
            checkbox.setChecked(False)

        # Check specified presets
        if preset_names:
            for name in preset_names:
                if name in self._preset_checkboxes:
                    self._preset_checkboxes[name].setChecked(True)

        # Clear and set custom patterns
        if self._custom_patterns_list is not None:
            self._custom_patterns_list.clear()
            if custom_patterns:
                for pattern in custom_patterns:
                    self._custom_patterns_list.addItem(pattern)

        self.patterns_changed.emit()

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to dictionary for state persistence.

        Returns:
            Dictionary with 'selected_presets' and 'custom_patterns'
        """
        selected_presets: list[str] = []
        for name, checkbox in self._preset_checkboxes.items():
            if checkbox.isChecked():
                selected_presets.append(name)

        custom_patterns: list[str] = []
        if self._custom_patterns_list is not None:
            for i in range(self._custom_patterns_list.count()):
                item = self._custom_patterns_list.item(i)
                if item:
                    custom_patterns.append(item.text())

        return {
            "selected_presets": selected_presets,
            "custom_patterns": custom_patterns,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore from dictionary.

        Args:
            data: Dictionary with 'selected_presets' and 'custom_patterns'
        """
        selected_presets = data.get("selected_presets", [])
        custom_patterns = data.get("custom_patterns", [])
        self.set_patterns(preset_names=selected_presets,
                          custom_patterns=custom_patterns)
