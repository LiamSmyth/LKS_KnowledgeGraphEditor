"""
QPasswordEntryComponent - Reusable password input field with show/hide toggle.

Provides a clean interface for password entry with optional confirmation.
Can be used standalone or embedded in forms.
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
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class QPasswordEntryComponent(QWidget):
    """
    Password input field with show/hide toggle button.

    **Features**:
    - Password masking (•••)
    - Show/hide toggle button (👁)
    - Optional confirmation field with match validation
    - Real-time match indicator
    - Signals for value changes

    **Interface**:
    - `get_password()` → str
    - `set_password(pwd)` → None
    - `clear()` → None
    - `is_valid()` → bool  (always True for single, checks match for confirmed)
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None
    - `set_enabled(enabled)` → None

    **Signals**:
    - `password_changed(password: str)` - Emitted when password changes
    - `valid_changed(is_valid: bool)` - Emitted when validation state changes

    **Example**:
    ```python
    # Simple password entry
    password = QPasswordEntryComponent(label="Password:")
    pwd = password.get_password()

    # With confirmation
    password = QPasswordEntryComponent(
        label="New Password:",
        require_confirmation=True,
        on_change=lambda pwd: print(f"Valid: {password.is_valid()}")
    )
    ```
    """

    password_changed = Signal(str)
    valid_changed = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "Password:",
        require_confirmation: bool = False,
        min_length: int = 0,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        """
        Initialize password entry component.

        Args:
            parent: Parent widget.
            label: Label text for the password field.
            require_confirmation: Whether to show confirmation field.
            min_length: Minimum password length (0 = no minimum).
            on_change: Callback when password changes (receives password string).
        """
        super().__init__(parent)

        self._require_confirmation = require_confirmation
        self._min_length = min_length
        self._on_change_callback = on_change
        self._is_valid = not require_confirmation  # Single field always valid

        self._setup_ui(label)

        # Connect callbacks
        if on_change:
            self.password_changed.connect(on_change)

    def _setup_ui(self, label: str) -> None:
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Password field row
        password_row = QHBoxLayout()

        self._password_label = QLabel(label)
        self._password_label.setFixedWidth(120)
        password_row.addWidget(self._password_label)

        self._password_entry = QLineEdit()
        self._password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_entry.setPlaceholderText("Enter password")
        self._password_entry.textChanged.connect(self._on_password_changed)
        password_row.addWidget(self._password_entry)

        self._show_btn = QPushButton("👁")
        self._show_btn.setFixedWidth(40)
        self._show_btn.setToolTip("Show/hide password")
        self._show_btn.setCheckable(True)
        self._show_btn.toggled.connect(self._toggle_visibility)
        password_row.addWidget(self._show_btn)

        layout.addLayout(password_row)

        # Confirmation field (if required)
        if self._require_confirmation:
            confirm_row = QHBoxLayout()

            confirm_label = QLabel("Confirm:")
            confirm_label.setFixedWidth(120)
            confirm_row.addWidget(confirm_label)

            self._confirm_entry = QLineEdit()
            self._confirm_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self._confirm_entry.setPlaceholderText("Repeat password")
            self._confirm_entry.textChanged.connect(self._on_password_changed)
            confirm_row.addWidget(self._confirm_entry)

            self._show_confirm_btn = QPushButton("👁")
            self._show_confirm_btn.setFixedWidth(40)
            self._show_confirm_btn.setToolTip("Show/hide confirmation")
            self._show_confirm_btn.setCheckable(True)
            self._show_confirm_btn.toggled.connect(
                self._toggle_confirm_visibility)
            confirm_row.addWidget(self._show_confirm_btn)

            layout.addLayout(confirm_row)

            # Match indicator
            self._match_label = QLabel("")
            self._match_label.setStyleSheet("color: gray; font-style: italic;")
            self._match_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self._match_label)

    def _toggle_visibility(self, checked: bool) -> None:
        """Toggle password visibility."""
        if checked:
            self._password_entry.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._password_entry.setEchoMode(QLineEdit.EchoMode.Password)

    def _toggle_confirm_visibility(self, checked: bool) -> None:
        """Toggle confirmation field visibility."""
        if checked:
            self._confirm_entry.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._confirm_entry.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_password_changed(self) -> None:
        """Handle password or confirmation change."""
        password = self._password_entry.text()

        # Validate
        old_valid = self._is_valid
        self._is_valid = self._validate()

        # Update match indicator if confirmation required
        if self._require_confirmation:
            pwd = self._password_entry.text()
            conf = self._confirm_entry.text()

            if not pwd and not conf:
                self._match_label.setText("")
                self._match_label.setStyleSheet(
                    "color: gray; font-style: italic;")
            elif pwd == conf and pwd:
                if self._min_length > 0 and len(pwd) < self._min_length:
                    self._match_label.setText(
                        f"⚠ Passwords match but too short (min {self._min_length})"
                    )
                    self._match_label.setStyleSheet(
                        "color: orange; font-style: italic;")
                else:
                    self._match_label.setText("✓ Passwords match")
                    self._match_label.setStyleSheet(
                        "color: green; font-style: italic;")
            else:
                self._match_label.setText("✗ Passwords do not match")
                self._match_label.setStyleSheet(
                    "color: red; font-style: italic;")

        # Emit signals
        self.password_changed.emit(password)
        if old_valid != self._is_valid:
            self.valid_changed.emit(self._is_valid)

    def _validate(self) -> bool:
        """Validate current password state.

        Returns:
            True if valid, False otherwise.
        """
        password = self._password_entry.text()

        # Check minimum length
        if self._min_length > 0 and len(password) < self._min_length:
            return False

        # Check confirmation match if required
        if self._require_confirmation:
            confirmation = self._confirm_entry.text()
            if password != confirmation or not password:
                return False

        return True

    def get_password(self) -> str:
        """
        Get the current password.

        Returns:
            Password string.
        """
        return self._password_entry.text()

    def set_password(self, password: str) -> None:
        """
        Set the password value.

        Args:
            password: Password to set.
        """
        self._password_entry.setText(password)
        if self._require_confirmation:
            self._confirm_entry.setText(password)

    def clear(self) -> None:
        """Clear the password fields."""
        self._password_entry.clear()
        if self._require_confirmation:
            self._confirm_entry.clear()
        if hasattr(self, "_match_label"):
            self._match_label.setText("")

    def is_valid(self) -> bool:
        """
        Check if the password is valid.

        Returns:
            True if valid (matches and meets min length), False otherwise.
        """
        return self._is_valid

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Note: Password values are NOT serialized for security.

        Returns:
            Dict with configuration (not values).
        """
        return {
            "require_confirmation": self._require_confirmation,
            "min_length": self._min_length,
            "label": self._password_label.text(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Note: Only configuration is restored, not password values.

        Args:
            data: Dict with configuration.
        """
        # Configuration is set at __init__, not runtime-changeable
        # This method exists for interface consistency
        pass

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: True to enable, False to disable.
        """
        self._password_entry.setEnabled(enabled)
        self._show_btn.setEnabled(enabled)
        if self._require_confirmation:
            self._confirm_entry.setEnabled(enabled)
            self._show_confirm_btn.setEnabled(enabled)
