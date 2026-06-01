"""UI component for LineSelectRule configuration."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS


class LineSelectRuleUI(QWidget):
    """UI component for configuring LineSelectRule.

    Provides:
    - Line index input field
    - Help text with examples
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize line select rule UI.

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
            "<b>Line Select:</b> Extracts a specific line from multi-line text.<br>"
            "<b>Example:</b> Index <code>1</code> on \"line1\\nline2\\nline3\" → extracts \"line2\""
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet(
            f"color: {COLORS['info']}; padding: 5px; background: #2a2a2a; border-radius: 3px;"
        )
        layout.addWidget(help_label)

        # Index field
        line_layout = QHBoxLayout()
        line_label = QLabel("Line Index:")
        line_label.setToolTip("Which line to extract (0 = first, -1 = last)")
        line_layout.addWidget(line_label)

        self._index_edit = QLineEdit()
        self._index_edit.setPlaceholderText("0 (or negative for from end)")
        self._index_edit.setToolTip(
            "0-based index:\n"
            "  0 = first line\n"
            "  1 = second line\n"
            "  -1 = last line\n"
            "  -2 = second to last"
        )
        line_layout.addWidget(self._index_edit)

        layout.addLayout(line_layout)

    def get_config(self) -> dict[str, Any]:
        """Get current configuration.

        Returns:
            Dictionary with 'index' key
        """
        index_text = self._index_edit.text().strip()
        index = int(index_text) if index_text else 0
        return {"index": index}

    def set_config(self, config: dict[str, Any]) -> None:
        """Set configuration.

        Args:
            config: Dictionary with 'index' or 'line_index' key
        """
        # Support both 'index' and 'line_index' for backwards compatibility
        index = config.get("index") or config.get("line_index", 0)
        self._index_edit.setText(str(index))

    def validate(self) -> tuple[bool, str]:
        """Validate current configuration.

        Returns:
            Tuple of (is_valid, error_message)
        """
        index_text = self._index_edit.text().strip()
        if index_text:
            try:
                int(index_text)
            except ValueError:
                return False, "Index must be a valid integer"

        return True, ""
