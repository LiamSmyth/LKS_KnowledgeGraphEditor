"""
Abstract base class for configuration UI components.

Defines standard interface for ConfigUI components that bind to
configuration dataclasses.
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


from abc import abstractmethod
from typing import Any

from PySide6.QtWidgets import QWidget


class QConfigUIBase(QWidget):
    """
    Abstract base class for ConfigUI components.

    ConfigUI components provide UI widgets bound to configuration dataclasses.
    They enforce a standard interface for getting/setting config and validation.

    Note: Does not use ABC to avoid metaclass conflicts with QWidget.
    Subclasses should implement the abstract methods.

    Usage:
        class QMyConfigUI(QConfigUIBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._build_ui()

            def _build_ui(self):
                # Create widgets...
                pass

            def get_config(self) -> MyConfig:
                return MyConfig(
                    param1=self._param1_input.text(),
                    param2=self._param2_input.value(),
                )

            def set_config(self, config: MyConfig) -> None:
                self._param1_input.setText(config.param1)
                self._param2_input.setValue(config.param2)

            def validate(self) -> tuple[bool, str]:
                if not self._param1_input.text():
                    return (False, "Param1 cannot be empty")
                return (True, "")
    """

    def get_config(self) -> Any:
        """
        Get current configuration from UI widgets.

        Returns:
            Configuration dataclass instance
        """
        raise NotImplementedError("Subclass must implement get_config()")

    def set_config(self, config: Any) -> None:
        """
        Set UI widgets from configuration dataclass.

        Args:
            config: Configuration dataclass instance
        """
        raise NotImplementedError("Subclass must implement set_config()")

    def validate(self) -> tuple[bool, str]:
        """
        Validate current UI input.

        Returns:
            Tuple of (is_valid, error_message).
            If valid, error_message should be empty string.
        """
        raise NotImplementedError("Subclass must implement validate()")


__all__ = ["QConfigUIBase"]
