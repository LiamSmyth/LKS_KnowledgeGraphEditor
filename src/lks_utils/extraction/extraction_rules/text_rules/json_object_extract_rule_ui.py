"""UI component for JsonObjectExtractRule configuration."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS


class JsonObjectExtractRuleUI(QWidget):
    """UI component for configuring JsonObjectExtractRule.

    This rule requires no configuration - it automatically extracts
    the first JSON object found in the text.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize JSON object extract rule UI.

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
            "<b>JSON Object Extract:</b> Finds and extracts the first JSON object.<br>"
            "<b>Example:</b> Text \"Response: {\\\"status\\\": \\\"ok\\\", \\\"code\\\": 200}\" → extracts the JSON object<br>"
            "Can then be chained with other rules to extract specific keys."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        info_label = QLabel(
            "Automatically detects and extracts JSON objects from text.\n"
            "No configuration needed - just extracts first {} object found."
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
