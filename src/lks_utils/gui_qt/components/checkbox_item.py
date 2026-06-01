"""
QCheckboxItemComponent - Reusable checkbox row with label and description.

Provides a clean interface for creating consistent checkbox rows
with primary label, optional description, and status indicator.
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QWidget,
)


class QCheckboxItemComponent(QWidget):
    """
    Single checkbox row with label, description, and optional status.

    **Features**:
    - Primary label (bold, clickable)
    - Optional description text (gray, smaller)
    - Optional status indicator (right-aligned)
    - Signals for state changes
    - Consistent styling for lists

    **Interface**:
    - `is_checked()` → bool
    - `set_checked(checked)` → None
    - `get_label()` → str
    - `set_status(text, color)` → None
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None
    - `set_enabled(enabled)` → None

    **Signals**:
    - `toggled(checked: bool)` - Emitted when checkbox state changes

    **Example**:
    ```python
    # Simple checkbox
    item = QCheckboxItemComponent(
        label="Enable feature",
        checked=True,
        on_toggle=lambda checked: print(f"Toggled: {checked}")
    )

    # With description and status
    item = QCheckboxItemComponent(
        label="Stock Dashboard",
        description="Web-based charting with tray control",
        status_text="✓ Active",
        status_color="green",
        checked=True
    )
    ```
    """

    toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "",
        description: str = "",
        checked: bool = False,
        status_text: str = "",
        status_color: str = "gray",
        on_toggle: Callable[[bool], None] | None = None,
    ) -> None:
        """
        Initialize checkbox item component.

        Args:
            parent: Parent widget.
            label: Primary label text (bold).
            description: Optional description text (gray, smaller).
            checked: Initial checked state.
            status_text: Optional status text (right-aligned).
            status_color: Color for status text ("green", "red", "orange", "gray").
            on_toggle: Callback when checkbox state changes.
        """
        super().__init__(parent)

        self._on_toggle_callback = on_toggle

        self._setup_ui(
            label, description, checked, status_text, status_color
        )

        # Connect callbacks
        if on_toggle:
            self.toggled.connect(on_toggle)

    def _setup_ui(
        self,
        label: str,
        description: str,
        checked: bool,
        status_text: str,
        status_color: str,
    ) -> None:
        """Set up the user interface."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(10)

        # Checkbox with label
        self._checkbox = QCheckBox(label)
        self._checkbox.setChecked(checked)
        self._checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self._checkbox)

        # Description label (if provided)
        if description:
            self._desc_label = QLabel(f"  - {description}")
            self._desc_label.setStyleSheet(
                "color: gray; font-size: 8pt; font-style: italic;"
            )
            layout.addWidget(self._desc_label)
        else:
            self._desc_label = None

        layout.addStretch()

        # Status label (if provided)
        if status_text:
            self._status_label = QLabel(status_text)
            self._status_label.setStyleSheet(
                f"color: {status_color}; font-size: 8pt;"
            )
            self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(self._status_label)
        else:
            self._status_label = None

    def _on_toggled(self, checked: bool) -> None:
        """Handle checkbox toggle."""
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        """
        Get the checked state.

        Returns:
            True if checked, False otherwise.
        """
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        """
        Set the checked state.

        Args:
            checked: True to check, False to uncheck.
        """
        self._checkbox.setChecked(checked)

    def get_label(self) -> str:
        """
        Get the label text.

        Returns:
            Label string.
        """
        return self._checkbox.text()

    def set_label(self, label: str) -> None:
        """
        Set the label text.

        Args:
            label: New label text.
        """
        self._checkbox.setText(label)

    def get_description(self) -> str:
        """
        Get the description text.

        Returns:
            Description string or empty string if no description.
        """
        if self._desc_label:
            text = self._desc_label.text()
            # Strip "  - " prefix if present
            if text.startswith("  - "):
                return text[4:]
            return text
        return ""

    def set_description(self, description: str) -> None:
        """
        Set the description text.

        Args:
            description: New description text.
        """
        if self._desc_label:
            self._desc_label.setText(
                f"  - {description}" if description else "")
            self._desc_label.setVisible(bool(description))

    def set_status(self, text: str, color: str = "gray") -> None:
        """
        Set or update the status indicator.

        Args:
            text: Status text (e.g., "✓ Active", "Disabled").
            color: Color name ("green", "red", "orange", "gray", etc.).
        """
        if self._status_label:
            self._status_label.setText(text)
            self._status_label.setStyleSheet(
                f"color: {color}; font-size: 8pt;"
            )
        else:
            # Create status label if it doesn't exist
            layout = self.layout()
            self._status_label = QLabel(text)
            self._status_label.setStyleSheet(
                f"color: {color}; font-size: 8pt;"
            )
            self._status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            layout.addWidget(self._status_label)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Returns:
            Dict with current state.
        """
        return {
            "label": self.get_label(),
            "description": self.get_description(),
            "checked": self.is_checked(),
            "status_text": (
                self._status_label.text() if self._status_label else ""
            ),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with state.
        """
        if "label" in data:
            self.set_label(data["label"])
        if "description" in data:
            self.set_description(data["description"])
        if "checked" in data:
            self.set_checked(data["checked"])
        if "status_text" in data and self._status_label:
            self._status_label.setText(data["status_text"])

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: True to enable, False to disable.
        """
        self._checkbox.setEnabled(enabled)
