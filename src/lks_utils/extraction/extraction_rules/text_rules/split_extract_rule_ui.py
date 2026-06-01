"""UI component for SplitExtractRule configuration."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS


class SplitExtractRuleUI(QWidget):
    """UI component for configuring SplitExtractRule.

    Provides:
    - Delimiter input field
    - Index input field
    - Help text with examples
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize split extract rule UI.

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
            "<b>Split Extract:</b> Splits text by delimiter and extracts one element.<br>"
            "<b>Example:</b> Delimiter <code>,</code> index <code>1</code> on \"apple,banana,cherry\" → extracts \"banana\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        # Delimiter field
        delim_layout = QHBoxLayout()
        delim_label = QLabel("Delimiter:")
        delim_label.setToolTip(
            "Character(s) to split on (e.g., comma, space, pipe)")
        delim_layout.addWidget(delim_label)

        self._delimiter_edit = QLineEdit()
        self._delimiter_edit.setPlaceholderText(",")
        self._delimiter_edit.setToolTip(
            "Examples: ',' or '|' or ' - ' or '\\t' (tab)")
        delim_layout.addWidget(self._delimiter_edit)

        layout.addLayout(delim_layout)

        # Index field
        index_layout = QHBoxLayout()
        index_label = QLabel("Element Index:")
        index_label.setToolTip(
            "Which piece to extract (0 = first, 1 = second, -1 = last)")
        index_layout.addWidget(index_label)

        self._index_edit = QLineEdit()
        self._index_edit.setPlaceholderText("0")
        self._index_edit.setToolTip(
            "0-based index. Use negative numbers to count from end.")
        index_layout.addWidget(self._index_edit)

        layout.addLayout(index_layout)

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Dictionary with 'delimiter' and 'index' keys
        """
        index_text = self._index_edit.text().strip()
        index = int(index_text) if index_text else 0
        return {
            "delimiter": self._delimiter_edit.text(),
            "index": index,
        }

    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration.

        Args:
            config: Dictionary with 'delimiter' and 'index' keys
        """
        if "delimiter" in config:
            self._delimiter_edit.setText(config["delimiter"])
        if "index" in config:
            self._index_edit.setText(str(config["index"]))

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        delimiter = self._delimiter_edit.text()
        if not delimiter:
            return False, "Delimiter is required"

        index_text = self._index_edit.text().strip()
        if index_text:
            try:
                int(index_text)
            except ValueError:
                return False, "Index must be a valid integer"

        return True, ""
