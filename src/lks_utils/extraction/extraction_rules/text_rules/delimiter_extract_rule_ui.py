"""UI component for DelimiterExtractRule configuration."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS


class DelimiterExtractRuleUI(QWidget):
    """UI component for configuring DelimiterExtractRule.

    Provides:
    - Start delimiter input field
    - End delimiter input field
    - Help text with examples
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize delimiter extract rule UI.

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
            "<b>Delimiter Extract:</b> Extracts text between two delimiters.<br>"
            "<b>Example:</b> Start <code>[</code> End <code>]</code> on \"Error: [404] Not Found\" → extracts \"404\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        # Start delimiter
        start_layout = QHBoxLayout()
        start_label = QLabel("Start Delimiter:")
        start_label.setToolTip("Text that marks the beginning of extraction")
        start_layout.addWidget(start_label)

        self._start_edit = QLineEdit()
        self._start_edit.setPlaceholderText("e.g., [")
        self._start_edit.setToolTip("Examples: '[' or 'START:' or '(' or '<'")
        start_layout.addWidget(self._start_edit)

        layout.addLayout(start_layout)

        # End delimiter
        end_layout = QHBoxLayout()
        end_label = QLabel("End Delimiter:")
        end_label.setToolTip("Text that marks the end of extraction")
        end_layout.addWidget(end_label)

        self._end_edit = QLineEdit()
        self._end_edit.setPlaceholderText("e.g., ]")
        self._end_edit.setToolTip("Examples: ']' or 'END' or ')' or '>'")
        end_layout.addWidget(self._end_edit)

        layout.addLayout(end_layout)

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Dictionary with 'start' and 'end' keys
        """
        return {
            "start": self._start_edit.text(),
            "end": self._end_edit.text(),
        }

    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration.

        Args:
            config: Dictionary with 'start'/'start_delimiter' and 'end'/'end_delimiter' keys
        """
        # Support both old and new naming
        start = config.get("start") or config.get("start_delimiter", "")
        end = config.get("end") or config.get("end_delimiter", "")
        self._start_edit.setText(start)
        self._end_edit.setText(end)

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        start = self._start_edit.text().strip()
        end = self._end_edit.text().strip()

        if not start:
            return False, "Start delimiter is required"
        if not end:
            return False, "End delimiter is required"

        return True, ""
