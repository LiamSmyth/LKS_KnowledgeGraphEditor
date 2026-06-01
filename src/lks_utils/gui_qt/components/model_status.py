"""Model status indicator component for PySide6.

Displays model availability status with indicator (✓/✗/?), model name,
and optional additional information. Supports custom status check callbacks.

Example:
    def check_ram_model(model_name: str) -> tuple[bool, str]:
        path = Path(f"/models/{model_name}")
        if path.exists():
            return True, f"Available at {path}"
        return False, "Not found"
    
    component = QModelStatusComponent(
        parent=parent,
        label="RAM Model:",
        model_name="ram_plus_swin_large_14m.pth",
        check_callback=check_ram_model
    )
    
    # Later update
    component.set_model_name("ram_swin_large_14m.pth")
    component.update_status()
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


from typing import Callable, Any
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QVBoxLayout, QPushButton
)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont


class QModelStatusComponent(QWidget):
    """Component displaying model availability status with indicator.

    Shows a status indicator (✓ = available, ✗ = not found, ? = unknown/error)
    along with model name and optional details text.

    Signals:
        status_changed: Emitted when status changes (bool: available, str: details)
        refresh_requested: Emitted when user requests status refresh
    """

    status_changed = Signal(bool, str)  # (available, details)
    refresh_requested = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "Model:",
        model_name: str = "",
        check_callback: Callable[[str], tuple[bool, str]] | None = None,
        show_refresh_button: bool = False
    ):
        """Initialize the model status component.

        Args:
            parent: Parent widget
            label: Label text (e.g., "RAM Model:", "CLIP Model:")
            model_name: Name of the model to check
            check_callback: Function that checks model status.
                Should return (exists: bool, details: str).
                Example: lambda name: (Path(name).exists(), "Path: /models/ram")
            show_refresh_button: Whether to show a refresh button
        """
        super().__init__(parent)

        self._model_name = model_name
        self._check_callback = check_callback
        self._last_status: bool | None = None
        self._last_details: str = ""

        self._setup_ui(label, show_refresh_button)

        # Initial status update if callback provided
        if self._check_callback and self._model_name:
            self.update_status()

    def _setup_ui(self, label: str, show_refresh_button: bool) -> None:
        """Create the UI layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Label (e.g., "Model:")
        self.label_widget = QLabel(label)
        layout.addWidget(self.label_widget)

        # Model name label
        self.model_label = QLabel(self._model_name)
        layout.addWidget(self.model_label)

        # Status indicator
        self.status_indicator = QLabel("?")
        status_font = QFont()
        status_font.setPointSize(12)
        status_font.setBold(True)
        self.status_indicator.setFont(status_font)
        self.status_indicator.setFixedWidth(20)
        layout.addWidget(self.status_indicator)

        # Details label (optional info text)
        self.details_label = QLabel("")
        font = QFont()
        font.setPointSize(8)
        self.details_label.setFont(font)
        self.details_label.setStyleSheet("color: gray;")
        layout.addWidget(self.details_label)

        # Refresh button (optional)
        if show_refresh_button:
            self.refresh_btn = QPushButton("⟳")
            self.refresh_btn.setFixedWidth(30)
            self.refresh_btn.clicked.connect(self._on_refresh_clicked)
            layout.addWidget(self.refresh_btn)
        else:
            self.refresh_btn = None

        layout.addStretch()

    def set_model_name(self, model_name: str) -> None:
        """Set the model name and update display.

        Args:
            model_name: New model name
        """
        self._model_name = model_name
        self.model_label.setText(model_name)
        # Don't auto-update status - caller should explicitly call update_status()

    def get_model_name(self) -> str:
        """Get the current model name.

        Returns:
            Current model name
        """
        return self._model_name

    def set_check_callback(self, callback: Callable[[str], tuple[bool, str]] | None) -> None:
        """Set the status check callback.

        Args:
            callback: Function that checks model status (model_name) -> (exists, details)
        """
        self._check_callback = callback

    @Slot()
    def update_status(self) -> None:
        """Update the status indicator by calling check_callback.

        If no callback is set, status remains at "?" (unknown).
        Emits status_changed signal if status changes.
        """
        if not self._check_callback:
            self._set_status(None, "No status check configured")
            return

        try:
            exists, details = self._check_callback(self._model_name)
            self._set_status(exists, details)
        except Exception as e:
            self._set_status(None, f"Error checking status: {e}")

    def _set_status(self, available: bool | None, details: str = "") -> None:
        """Set the status indicator and details.

        Args:
            available: True if model available, False if not, None if unknown
            details: Additional information text
        """
        prev_status = self._last_status
        self._last_status = available
        self._last_details = details

        if available is True:
            self.status_indicator.setText("✓")
            self.status_indicator.setStyleSheet("color: green;")
        elif available is False:
            self.status_indicator.setText("✗")
            self.status_indicator.setStyleSheet("color: red;")
        else:
            self.status_indicator.setText("?")
            self.status_indicator.setStyleSheet("color: gray;")

        self.details_label.setText(details)

        # Emit signal if status changed
        if prev_status != available:
            self.status_changed.emit(
                available if available is not None else False, details)

    def get_status(self) -> tuple[bool | None, str]:
        """Get the current status.

        Returns:
            Tuple of (available, details). available is None if unknown.
        """
        return self._last_status, self._last_details

    def is_available(self) -> bool:
        """Check if model is marked as available.

        Returns:
            True if model is available, False otherwise (including unknown)
        """
        return self._last_status is True

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self.update_status()
        self.refresh_requested.emit()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: Whether to enable the component
        """
        self.setEnabled(enabled)
        if self.refresh_btn:
            self.refresh_btn.setEnabled(enabled)

    # State persistence
    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dictionary.

        Returns:
            Dictionary with model_name, last_status, last_details
        """
        return {
            "model_name": self._model_name,
            "last_status": self._last_status,
            "last_details": self._last_details,
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore component state from dictionary.

        Args:
            state: Dictionary from to_dict()
        """
        if "model_name" in state:
            self.set_model_name(state["model_name"])

        # Restore last known status (but don't emit signals)
        if "last_status" in state and "last_details" in state:
            self._last_status = state["last_status"]
            self._last_details = state["last_details"]
            # Re-apply visual state
            self._set_status(self._last_status, self._last_details)
