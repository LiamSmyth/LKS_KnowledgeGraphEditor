"""
QPatternBuilderComponent - Visual pattern builder for text extraction rules.

Provides a user-friendly interface for building extraction patterns
without knowing regex syntax. Supports:

- Prefix: plain text prefix matching (e.g. ``[Note]``)
- Delimiter: start/end tag extraction (e.g. ``[Summary]|||[End Summary]``)
- Line matching: contains, starts with, ends with, equals
- Span extraction: between start/end tags
- Section extraction: header to next header
- Custom: manual regex entry

Generates valid patterns for text extraction engines.
"""

from __future__ import annotations
import sys

# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(
            None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass

import re
import json
from pathlib import Path
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme.colors import COLORS
from .library_component import QLibraryComponent
from .pattern_builder_type import PatternBuilderType
from .pattern_builder_types import (
    CustomPatternBuilderType,
    DelimiterPatternBuilderType,
    LinePatternBuilderType,
    PrefixPatternBuilderType,
    SectionPatternBuilderType,
    SpanPatternBuilderType,
)


class QPatternBuilderComponent(QWidget):
    """
    Visual pattern builder for text extraction.

    Provides a user-friendly interface for building patterns without requiring
    regex knowledge. Pattern and matches update in real-time as fields change.

    Supported builder types (``get_pattern()`` returns the type_id as second element):

    - ``"prefix"``    — plain-text prefix; outputs a bare prefix string
    - ``"delimiter"`` — start/end tags; outputs ``"start|||end"``
    - ``"line"``      — regex: matches a single line by predicate
    - ``"span"``      — regex: extracts text between two tags
    - ``"section"``   — regex: extracts a header + body section
    - ``"custom"``    — regex: manual entry

    **Interface:**
    - ``get_pattern()`` → ``tuple[str, str]``  # (pattern, type_id)
    - ``set_pattern(pattern, hook_type)`` → ``None``
    - ``to_dict()`` → ``dict[str, Any]``
    - ``from_dict(data)`` → ``None``

    **Example:**

    .. code-block:: python

        builder = QPatternBuilderComponent()
        layout.addWidget(builder)

        # Get the current pattern when needed
        pattern, type_id = builder.get_pattern()
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(800)

        # Pattern builder types — prefix/delimiter first so they appear first
        self._pattern_types: dict[str, PatternBuilderType] = {
            "prefix": PrefixPatternBuilderType(),
            "delimiter": DelimiterPatternBuilderType(),
            "line": LinePatternBuilderType(),
            "span": SpanPatternBuilderType(),
            "section": SectionPatternBuilderType(),
            "custom": CustomPatternBuilderType(),
        }
        self._current_type: PatternBuilderType | None = None

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # Library toolbar at the top
        library_dir = Path(__file__).parent / "data" / "patterns"
        self._library = QLibraryComponent(
            parent=self,
            library_dir=library_dir,
            file_filter="Pattern Files (*.json);;All Files (*)",
            file_extension=".json",
            label="Pattern:",
        )
        self._library.data_requested.connect(self._on_library_save)
        self._library.data_loaded.connect(self._on_library_load)
        layout.addWidget(self._library)

        # Header
        header_layout = QHBoxLayout()
        title = QLabel("Pattern Builder")
        title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        header_layout.addWidget(title)

        subtitle = QLabel("Build extraction patterns visually")
        subtitle.setStyleSheet(f"color: {COLORS['light']};")
        header_layout.addWidget(subtitle)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Pattern Type Selection
        type_group = QGroupBox("Pattern Type")
        type_layout = QHBoxLayout(type_group)
        type_layout.addWidget(QLabel("Select pattern mode:"))

        self._type_combo = QComboBox()
        for type_id, pattern_type in self._pattern_types.items():
            self._type_combo.addItem(pattern_type.get_type_name(), type_id)
        self._type_combo.setCurrentIndex(0)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self._type_combo)

        # "Include matched text" — only meaningful for regex-output types
        self._include_match_check = QCheckBox("Include matched text")
        self._include_match_check.setToolTip(
            "Include the full matched line/text instead of just the extracted part.\n"
            "Example: Pattern for '[Note]' + content\n"
            "  • Unchecked (default): Returns just the content after [Note]\n"
            "  • Checked: Returns the entire line '[Note] content'"
        )
        self._include_match_check.stateChanged.connect(self._update_pattern)
        type_layout.addWidget(self._include_match_check)
        type_layout.addStretch()
        layout.addWidget(type_group)

        # Rule Configuration (changes based on pattern type)
        self._rule_container = QGroupBox("Configuration")
        self._rule_layout = QVBoxLayout(self._rule_container)
        self._type_ui_widget: QWidget | None = None
        layout.addWidget(self._rule_container)

        # Test Area
        test_group = QGroupBox("Pattern Testing")
        test_layout = QVBoxLayout(test_group)

        result_layout = QHBoxLayout()
        self._test_result_label = QLabel("No pattern yet")
        self._test_result_label.setStyleSheet(
            f"color: {COLORS['light']}; font-weight: bold;")
        result_layout.addWidget(self._test_result_label)
        result_layout.addStretch()
        test_layout.addLayout(result_layout)

        # Two-column: sample text  |  matches
        columns_layout = QHBoxLayout()

        sample_column = QVBoxLayout()
        sample_label = QLabel("Sample text:")
        sample_label.setToolTip(
            "Enter sample text to test the pattern against")
        sample_column.addWidget(sample_label)

        self._sample_text = QTextEdit()
        self._sample_text.setMinimumHeight(100)
        self._sample_text.setPlainText(
            "[Note] This is a sample note.\n"
            "[Summary]\nHere is the summary content.\n[End Summary]"
        )
        self._sample_text.textChanged.connect(self._test_pattern)
        sample_column.addWidget(self._sample_text)
        columns_layout.addLayout(sample_column, 1)

        matches_column = QVBoxLayout()
        matches_column.addWidget(QLabel("Matches:"))

        self._matches_table = QTableWidget()
        self._matches_table.setColumnCount(1)
        self._matches_table.setHorizontalHeaderLabels(["Matched Text"])
        self._matches_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self._matches_table.setMinimumHeight(100)
        self._matches_table.setAlternatingRowColors(True)
        self._matches_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._matches_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self._matches_table.setWordWrap(True)
        self._matches_table.verticalHeader().setDefaultSectionSize(60)

        mono_font = QFont("Consolas", 9)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        self._matches_table.setFont(mono_font)
        matches_column.addWidget(self._matches_table)
        columns_layout.addLayout(matches_column, 1)

        test_layout.addLayout(columns_layout)
        layout.addWidget(test_group)

        # Generated Pattern Display
        pattern_group = QGroupBox("Generated Pattern")
        pattern_layout = QVBoxLayout(pattern_group)
        self._pattern_entry = QLineEdit()
        self._pattern_entry.setReadOnly(True)
        self._pattern_entry.setToolTip("The pattern that will be used")
        pattern_layout.addWidget(self._pattern_entry)
        layout.addWidget(pattern_group)

        # Initialise with the first type
        self._on_type_changed()

    # ------------------------------------------------------------------
    # Library persistence
    # ------------------------------------------------------------------

    def _on_library_save(self) -> None:
        """Library component requesting data to save."""
        pattern, _ = self.get_pattern()
        data: dict[str, Any] = {
            "name": self._library.current_file.stem if self._library.current_file else "Untitled",
            "pattern": pattern,
            "sample_text": self._sample_text.toPlainText(),
        }
        type_id = self._type_combo.currentData() if self._type_combo else "custom"
        data["builder_type"] = type_id
        if self._current_type:
            data["type_config"] = self._current_type.get_config()
        self._library.set_data(json.dumps(data, indent=2))

    def _on_library_load(self, content: str) -> None:
        """Library component loaded data from file."""
        try:
            data = json.loads(content)
            pattern = data.get("pattern", "")
            sample_text = data.get("sample_text", "")
            # Restore builder type if saved, otherwise fall back to custom
            builder_type = data.get("builder_type", "custom")
            idx = self._type_combo.findData(builder_type)
            if idx < 0:
                idx = self._type_combo.findData("custom")
            self._type_combo.setCurrentIndex(idx)
            if self._current_type:
                type_config = data.get("type_config")
                if type_config:
                    self._current_type.set_config(type_config)
                elif pattern:
                    # Legacy format: only pattern string was saved
                    self._current_type.set_config({"pattern": pattern})
            self._sample_text.setPlainText(sample_text)
            self._update_pattern()
        except (json.JSONDecodeError, KeyError) as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Load Error",
                                f"Failed to load pattern: {e}")

    # ------------------------------------------------------------------
    # Type / pattern updates
    # ------------------------------------------------------------------

    def _on_type_changed(self) -> None:
        """Handle pattern type selection change."""
        type_id = self._type_combo.currentData()
        if type_id not in self._pattern_types:
            return

        # Fully clear existing config widgets to avoid stale/overlapping UI
        # when switching types repeatedly.
        while self._rule_layout.count() > 0:
            item = self._rule_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._type_ui_widget = None

        # Create and show the new type UI
        self._current_type = self._pattern_types[type_id]
        self._current_type.set_on_change(self._update_pattern)
        self._type_ui_widget = self._current_type.create_ui(
            self._rule_container)
        self._rule_layout.addWidget(self._type_ui_widget)

        # Hide "Include matched text" for non-regex types (prefix/delimiter)
        self._include_match_check.setVisible(
            self._current_type.uses_regex_output())

        # Refresh pattern display
        self._update_pattern()

    def _update_pattern(self) -> None:
        """Update the generated pattern display and run the live test."""
        if self._current_type:
            include_match = self._include_match_check.isChecked()
            pattern = self._current_type.build_pattern(
                include_full_match=include_match)
            self._pattern_entry.setText(pattern)
            self._test_pattern()

    def _test_pattern(self) -> None:
        """Test the current pattern against the sample text."""
        pattern = self._pattern_entry.text()
        sample = self._sample_text.toPlainText()

        if not pattern:
            self._test_result_label.setText("No pattern")
            self._test_result_label.setStyleSheet(f"color: {COLORS['light']};")
            return

        try:
            # For non-regex types (prefix, delimiter) use type-specific matching
            custom_matches: list[str] | None = None
            if self._current_type:
                custom_matches = self._current_type.test_matches(sample)

            if custom_matches is not None:
                matches: list[Any] = custom_matches
                match_count = len(matches)
            else:
                raw = re.findall(pattern, sample, re.MULTILINE)
                matches = raw
                match_count = len(matches)

            if match_count > 0:
                self._test_result_label.setText(
                    f"✓ {match_count} match(es) found")
                self._test_result_label.setStyleSheet(
                    f"color: {COLORS['success']}; font-weight: bold;")

                self._matches_table.setRowCount(0)
                display_count = min(match_count, 50)
                self._matches_table.setRowCount(
                    display_count + (1 if match_count > 50 else 0))

                for i, m in enumerate(matches[:50]):
                    if isinstance(m, tuple):
                        m = m[0] if m else ""
                    text = str(m)
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    self._matches_table.setItem(i, 0, item)

                self._matches_table.resizeRowsToContents()

                if match_count > 50:
                    more_item = QTableWidgetItem(
                        f"... and {match_count - 50} more matches")
                    more_item.setFont(QFont("Consolas", 9))
                    self._matches_table.setItem(display_count, 0, more_item)
            else:
                self._test_result_label.setText("✗ No matches")
                self._test_result_label.setStyleSheet(
                    f"color: {COLORS['warning']}; font-weight: bold;")
                self._matches_table.setRowCount(0)

        except re.error as e:
            self._test_result_label.setText(f"✗ Invalid regex: {e}")
            self._test_result_label.setStyleSheet(
                f"color: {COLORS['danger']}; font-weight: bold;")
            self._matches_table.setRowCount(0)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_pattern(self) -> tuple[str, str]:
        """Return the current pattern and the active builder type id.

        Returns:
            ``(pattern, type_id)`` where *type_id* is one of ``"prefix"``,
            ``"delimiter"``, ``"line"``, ``"span"``, ``"section"``,
            ``"custom"``.
        """
        pattern = self._pattern_entry.text()
        type_id = self._type_combo.currentData() if self._type_combo else "custom"
        return (pattern, type_id)

    def get_include_match(self) -> bool:
        """Return the current *Include matched text* checkbox state."""
        return self._include_match_check.isChecked()

    def set_include_match(self, include: bool) -> None:
        """Set the *Include matched text* checkbox state."""
        self._include_match_check.setChecked(include)

    def set_pattern(self, pattern: str, hook_type: str = "regex") -> None:
        """Load an existing pattern into the builder.

        Args:
            pattern: The pattern string to restore.
            hook_type: The hook type or builder type id.  Accepted values:
                ``"prefix"``, ``"delimiter"``, ``"regex"`` / ``"custom"``,
                ``"line"``, ``"span"``, ``"section"``.  Unknown values fall
                back to ``"custom"`` mode.
        """
        # Map generic hook_type names to specific builder types
        type_map: dict[str, str] = {"regex": "custom"}
        builder_type = type_map.get(hook_type, hook_type)

        idx = self._type_combo.findData(builder_type)
        if idx < 0:
            idx = self._type_combo.findData("custom")
            builder_type = "custom"
        self._type_combo.setCurrentIndex(idx)

        if self._current_type:
            if builder_type == "prefix":
                self._current_type.set_config({"prefix": pattern})
            elif builder_type == "delimiter":
                if "|||" in pattern:
                    start, _, end = pattern.partition("|||")
                    self._current_type.set_config(
                        {"start_tag": start, "end_tag": end})
                else:
                    self._current_type.set_config(
                        {"start_tag": pattern, "end_tag": ""})
            else:
                self._current_type.set_config({"pattern": pattern})
        self._update_pattern()

    def to_dict(self) -> dict[str, Any]:
        """Serialise component state to a dict for persistence.

        Returns:
            Dict with current configuration.
        """
        result: dict[str, Any] = {
            "pattern_type": self._type_combo.currentData(),
            "sample_text": self._sample_text.toPlainText(),
            "include_match": self._include_match_check.isChecked(),
        }
        if self._current_type:
            result["type_config"] = self._current_type.get_config()
        return result

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore component state from a dict.

        Args:
            data: Dict previously produced by :meth:`to_dict`.
        """
        type_id = data.get("pattern_type", "line")
        idx = self._type_combo.findData(type_id)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)

        if self._current_type and "type_config" in data:
            self._current_type.set_config(data["type_config"])

        if "sample_text" in data:
            self._sample_text.setPlainText(data["sample_text"])

        if "include_match" in data:
            self._include_match_check.setChecked(data["include_match"])

        self._update_pattern()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: ``True`` to enable, ``False`` to disable.
        """
        self.setEnabled(enabled)
