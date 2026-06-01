"""
Dual-mode widget pattern for standalone and embedded use.

Provides a common pattern for widgets that can be used both as
standalone windows and embedded in parent widgets.
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


from PySide6.QtWidgets import QMainWindow, QWidget


class QDualModeWidget(QWidget):
    """
    Base class for widgets that support both standalone and embedded modes.

    When used standalone, wraps widget in a QMainWindow.
    When embedded, returns the widget directly.

    Usage:
        class MyComponent(QDualModeWidget):
            def __init__(self, parent=None, standalone=False):
                super().__init__(parent)
                self._build_ui()

                if standalone:
                    self._setup_standalone()

            def _build_ui(self):
                # Build component UI
                pass

        # Standalone:
        widget = MyComponent(standalone=True)
        widget.show()

        # Embedded:
        widget = MyComponent(parent=main_window)
        layout.addWidget(widget)

    Note:
        The standalone pattern is useful for testing and development.
        Components should be designed to work in both modes.
    """

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize dual-mode widget.

        Args:
            parent: Parent widget (None for standalone)
        """
        super().__init__(parent)
        self._standalone_window: QMainWindow | None = None

    def _setup_standalone(
        self,
        title: str = "Component",
        width: int = 800,
        height: int = 600,
    ) -> QMainWindow:
        """
        Set up standalone mode with a main window wrapper.

        Args:
            title: Window title
            width: Window width
            height: Window height

        Returns:
            QMainWindow containing this widget
        """
        self._standalone_window = QMainWindow()
        self._standalone_window.setWindowTitle(title)
        self._standalone_window.resize(width, height)
        self._standalone_window.setCentralWidget(self)
        return self._standalone_window

    def show(self) -> None:
        """Show widget. If standalone, shows the window."""
        if self._standalone_window:
            self._standalone_window.show()
        else:
            super().show()

    def close(self) -> bool:
        """Close widget. If standalone, closes the window."""
        if self._standalone_window:
            return self._standalone_window.close()
        else:
            return super().close()


__all__ = ["QDualModeWidget"]
