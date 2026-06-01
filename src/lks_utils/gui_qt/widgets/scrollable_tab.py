"""
Scrollable tab widget for PySide6.

Port of lks_utils.gui.scrollable_tab.ScrollableTab to Qt.
Provides automatic vertical scrolling for tab content.
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


from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget


class QScrollableTab(QWidget):
    """
    A scrollable tab widget for use with QTabWidget.

    Automatically adds vertical scrolling when content exceeds the
    available space. When content fits, it stretches to fill the area
    without showing a scrollbar.

    Port of tkinter ScrollableTab to PySide6.

    Usage:
        from lks_utils.gui_qt.widgets import QScrollableTab

        tab_widget = QTabWidget(parent)
        tab = QScrollableTab()
        tab_widget.addTab(tab, "My Tab")

        # Add content to tab.content_layout instead of tab directly
        label = QLabel("Content")
        tab.content_layout.addWidget(label)

    Example:
        # Before (manual scroll area setup):
        tab = QWidget()
        scroll = QScrollArea(tab)
        content = QWidget()
        # ... setup scrolling ...
        tab_widget.addTab(tab, "My Tab")

        # After (using QScrollableTab):
        tab = QScrollableTab()
        tab_widget.addTab(tab, "My Tab")
        label = QLabel("Content")
        tab.content_layout.addWidget(label)

    Note:
        Qt's QScrollArea handles showing/hiding scrollbars automatically,
        so the implementation is simpler than the tkinter version.
    """

    def __init__(self, parent: QWidget | None = None):
        """
        Initialize scrollable tab.

        Args:
            parent: Parent widget (typically None for tabs)
        """
        super().__init__(parent)

        # Main layout for the tab
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)

        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(10, 10, 10, 10)

        # Set up hierarchy
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)


__all__ = ["QScrollableTab"]
