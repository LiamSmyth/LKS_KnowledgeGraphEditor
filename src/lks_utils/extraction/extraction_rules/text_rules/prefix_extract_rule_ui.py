"""UI component for PrefixExtractRule configuration."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS


class PrefixExtractRuleUI(QWidget):
    """UI component for configuring PrefixExtractRule.

    Provides:
    - Prefix input field
    - Help text with examples
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize prefix extract rule UI.

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
            "<b>Prefix Extract:</b> Finds line starting with prefix and extracts the rest.<br>"
            "<b>Example:</b> Prefix <code>Result: </code> on multi-line text with \"Result: SUCCESS\" → extracts \"SUCCESS\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        # Prefix field
        prefix_layout = QHBoxLayout()
        prefix_label = QLabel("Line Prefix:")
        prefix_label.setToolTip(
            "Text that appears at the start of the line to extract")
        prefix_layout.addWidget(prefix_label)

        self._prefix_edit = QLineEdit()
        self._prefix_edit.setPlaceholderText("e.g., 'Result: '")
        self._prefix_edit.setToolTip(
            "Examples:\n"
            "  'Error: ' - finds line starting with 'Error: '\n"
            "  'ID=' - finds line starting with 'ID='\n"
            "  '> ' - finds line starting with '> '"
        )
        prefix_layout.addWidget(self._prefix_edit)

        layout.addLayout(prefix_layout)

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Dictionary with 'prefix' key
        """
        return {"prefix": self._prefix_edit.text()}

    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration.

        Args:
            config: Dictionary with 'prefix' key
        """
        if "prefix" in config:
            self._prefix_edit.setText(config["prefix"])

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        prefix = self._prefix_edit.text().strip()
        if not prefix:
            return False, "Prefix is required"
        return True, ""
