"""UI component for RegexExtractRule configuration."""
from __future__ import annotations

from typing import Any
import re

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.components.pattern_builder import QPatternBuilderComponent
from lks_utils.gui_qt.theme import COLORS


class RegexExtractRuleUI(QWidget):
    """UI component for configuring RegexExtractRule.

    Provides:
    - Pattern input field
    - Capture group selector
    - Help text with examples

    Example:
        ui = RegexExtractRuleUI()
        layout.addWidget(ui)
        config = ui.get_config()  # {'pattern': '...', 'group': 0}
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize regex extract rule UI.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Help text
        help_label = QLabel(
            "<b>Regex Extract:</b> Uses regular expressions to extract text.<br>"
            "<b>Example:</b> Pattern <code>(\\d+)</code> on text \"Error: 404\" → extracts \"404\"<br>"
            "Use parentheses () to create capture groups."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        # Pattern field with builder button
        pattern_row = QHBoxLayout()

        pattern_label = QLabel("Pattern:")
        pattern_label.setToolTip(
            "Regular expression pattern. Use () for capture groups.")
        pattern_row.addWidget(pattern_label)

        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText(
            r"Enter regex pattern, e.g., (\d+)")
        self._pattern_edit.setToolTip(
            "Example patterns:\n"
            r"  (\d+) - captures one or more digits" "\n"
            r"  ([A-Z]{3}) - captures 3 uppercase letters" "\n"
            r"  ERROR: (.*) - captures everything after 'ERROR: '"
        )
        pattern_row.addWidget(self._pattern_edit)

        # Pattern builder button
        builder_btn = QPushButton("Pattern Builder...")
        builder_btn.setToolTip("Open visual pattern builder")
        builder_btn.clicked.connect(self._open_pattern_builder)
        pattern_row.addWidget(builder_btn)

        layout.addLayout(pattern_row)

        # Group selector
        group_layout = QHBoxLayout()
        group_label = QLabel("Capture Group:")
        group_label.setToolTip(
            "Capture groups let you extract specific parts of a match.\n"
            "Use parentheses () in your pattern to define groups.\n\n"
            "Example: Pattern r'\\[(.+?)\\] (.+)' on text '[Note] Content'\n"
            "  • Group 0: '[Note] Content' (full match)\n"
            "  • Group 1: 'Note' (first group)\n"
            "  • Group 2: 'Content' (second group)"
        )
        group_layout.addWidget(group_label)

        self._group_combo = QComboBox()
        self._group_combo.addItem("0 (full match)", 0)
        for i in range(1, 10):
            self._group_combo.addItem(f"Group {i}", i)
        self._group_combo.setToolTip(
            "Which capture group to extract:\n"
            "  • 0: Entire matched text\n"
            "  • 1: First (...) group in pattern\n"
            "  • 2: Second (...) group, etc.\n\n"
            "Example with r'ERROR: (.*)' on 'ERROR: disk full':\n"
            "  • Group 0 returns: 'ERROR: disk full'\n"
            "  • Group 1 returns: 'disk full'"
        )
        group_layout.addWidget(self._group_combo)
        group_layout.addStretch()

        layout.addLayout(group_layout)

        # Options checkboxes
        options_layout = QHBoxLayout()

        self._case_insensitive_check = QCheckBox("Case insensitive")
        self._case_insensitive_check.setToolTip(
            "Ignore case when matching (e.g., 'note' matches 'Note', 'NOTE', etc.)"
        )
        options_layout.addWidget(self._case_insensitive_check)

        self._include_match_check = QCheckBox("Include matched text")
        self._include_match_check.setToolTip(
            "Return the full matched text instead of just the capture group.\n"
            "Example: Pattern r'\\[Note\\](.*)' on '[Note] Text'\n"
            "  • Unchecked (default): Returns ' Text' (capture group only)\n"
            "  • Checked: Returns '[Note] Text' (full match)"
        )
        options_layout.addWidget(self._include_match_check)

        options_layout.addStretch()
        layout.addLayout(options_layout)

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Dictionary with 'pattern', 'group', 'flags', and 'include_match' keys
        """
        flags = 0
        if self._case_insensitive_check.isChecked():
            flags |= re.IGNORECASE

        return {
            "pattern": self._pattern_edit.text(),
            "group": self._group_combo.currentData(),
            "flags": flags,
            "include_match": self._include_match_check.isChecked(),
        }

    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration.

        Args:
            config: Dictionary with 'pattern', 'group', 'flags', and 'include_match' keys
        """
        if "pattern" in config:
            self._pattern_edit.setText(config["pattern"])
        if "group" in config:
            group = config["group"]
            idx = self._group_combo.findData(group)
            if idx >= 0:
                self._group_combo.setCurrentIndex(idx)
        if "flags" in config:
            flags = config["flags"]
            self._case_insensitive_check.setChecked(
                bool(flags & re.IGNORECASE))
        if "include_match" in config:
            self._include_match_check.setChecked(config["include_match"])

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        pattern = self._pattern_edit.text().strip()
        if not pattern:
            return False, "Pattern is required"
        return True, ""

    def _open_pattern_builder(self) -> None:
        """Open pattern builder dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Pattern Builder")
        dialog.setMinimumSize(600, 500)

        layout = QVBoxLayout(dialog)

        # Create pattern builder component
        builder = QPatternBuilderComponent(dialog)

        # Load current pattern if exists
        current_pattern = self._pattern_edit.text().strip()
        if current_pattern:
            builder.set_pattern(current_pattern, "regex")

        # Load current include_match state
        builder.set_include_match(self._include_match_check.isChecked())

        layout.addWidget(builder)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # If accepted, update pattern field and include_match checkbox
        if dialog.exec() == QDialog.Accepted:
            pattern, hook_type = builder.get_pattern()
            if hook_type == "regex":
                self._pattern_edit.setText(pattern)
            # Update include_match checkbox from builder
            self._include_match_check.setChecked(builder.get_include_match())
