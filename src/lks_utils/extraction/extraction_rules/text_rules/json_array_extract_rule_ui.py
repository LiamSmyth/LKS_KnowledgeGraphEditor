"""UI component for JsonArrayExtractRule configuration."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS


class JsonArrayExtractRuleUI(QWidget):
    """UI component for configuring JsonArrayExtractRule.

    This rule requires no configuration - it automatically extracts
    the first JSON array found in the text.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize JSON array extract rule UI.

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
            "<b>JSON Array Extract:</b> Finds and extracts the first JSON array.<br>"
            "<b>Example:</b> Text \"Items: [\\\"apple\\\", \\\"banana\\\", \\\"cherry\\\"]\" → extracts the array<br>"
            "Can be chained with other rules to extract specific elements."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        info_label = QLabel(
            "Automatically detects and extracts JSON arrays from text.\n"
            "No configuration needed - just extracts first [] array found."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(f"color: {COLORS['light']};")
        layout.addWidget(info_label)

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Empty dictionary (no configuration needed)
        """
        return {}

    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration.

        Args:
            config: Dictionary (ignored - no configuration needed)
        """
        pass

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Always returns (True, "") since no configuration is needed
        """
        return True, ""
