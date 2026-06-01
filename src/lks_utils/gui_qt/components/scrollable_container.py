"""
QScrollableContainer - Generic scrollable container widget.

Provides a reusable scrollable area with automatic scroll bar management
and mousewheel support. More flexible than QScrollableTab.
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


from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class QScrollableContainer(QWidget):
    """
    Generic scrollable container for any content.

    **Features**:
    - Automatic vertical/horizontal scrolling
    - Configurable scroll bar policies
    - Mousewheel support (built-in to QScrollArea)
    - Optional frame styling
    - Resizable content widget

    **Interface**:
    - `content_widget` - Add child widgets here
    - `content_layout` - VBoxLayout of content_widget
    - `scroll_area` - Access underlying QScrollArea
    - `set_scroll_policy(vertical, horizontal)` → None
    - `to_dict()` → dict[str, Any]
    - `from_dict(data)` → None

    **Example**:
    ```python
    # Create scrollable container
    container = QScrollableContainer(
        vertical_policy=Qt.ScrollBarAsNeeded,
        horizontal_policy=Qt.ScrollBarAlwaysOff
    )

    # Add content to container.content_layout
    for i in range(50):
        label = QLabel(f"Item {i}")
        container.content_layout.addWidget(label)

    # Or add to container.content_widget with custom layout
    ```
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        vertical_policy: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        horizontal_policy: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        show_frame: bool = False,
        margins: tuple[int, int, int, int] = (10, 10, 10, 10),
    ) -> None:
        """
        Initialize scrollable container.

        Args:
            parent: Parent widget.
            vertical_policy: Vertical scrollbar policy.
            horizontal_policy: Horizontal scrollbar policy.
            show_frame: Whether to show a frame around the scroll area.
            margins: Content margins (left, top, right, bottom).
        """
        super().__init__(parent)

        self._setup_ui(vertical_policy, horizontal_policy, show_frame, margins)

    def _setup_ui(
        self,
        vertical_policy: Qt.ScrollBarPolicy,
        horizontal_policy: Qt.ScrollBarPolicy,
        show_frame: bool,
        margins: tuple[int, int, int, int],
    ) -> None:
        """Set up the user interface."""
        # Main layout for the container
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(vertical_policy)
        self.scroll_area.setHorizontalScrollBarPolicy(horizontal_policy)

        if not show_frame:
            self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        # Content widget (what users add content to)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(*margins)

        # Set up hierarchy
        self.scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll_area)

    def set_scroll_policy(
        self,
        vertical: Qt.ScrollBarPolicy | None = None,
        horizontal: Qt.ScrollBarPolicy | None = None,
    ) -> None:
        """
        Update scroll bar policies.

        Args:
            vertical: Vertical scrollbar policy.
            horizontal: Horizontal scrollbar policy.
        """
        if vertical is not None:
            self.scroll_area.setVerticalScrollBarPolicy(vertical)
        if horizontal is not None:
            self.scroll_area.setHorizontalScrollBarPolicy(horizontal)

    def scroll_to_top(self) -> None:
        """Scroll to the top of the content."""
        self.scroll_area.verticalScrollBar().setValue(0)

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the content."""
        vbar = self.scroll_area.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def scroll_to_widget(self, widget: QWidget) -> None:
        """
        Scroll to make a specific widget visible.

        Args:
            widget: Widget to scroll to.
        """
        self.scroll_area.ensureWidgetVisible(widget)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize component state to dict.

        Note: Only configuration is saved, not content.

        Returns:
            Dict with current state.
        """
        return {
            "vertical_policy": int(self.scroll_area.verticalScrollBarPolicy()),
            "horizontal_policy": int(self.scroll_area.horizontalScrollBarPolicy()),
            "scroll_position": self.scroll_area.verticalScrollBar().value(),
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        """
        Restore component state from dict.

        Args:
            data: Dict with state.
        """
        if "vertical_policy" in data:
            self.scroll_area.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy(data["vertical_policy"])
            )
        if "horizontal_policy" in data:
            self.scroll_area.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy(data["horizontal_policy"])
            )
        if "scroll_position" in data:
            self.scroll_area.verticalScrollBar().setValue(
                data["scroll_position"])

    def set_enabled(self, enabled: bool) -> None:
        """
        Enable or disable the component.

        Args:
            enabled: True to enable, False to disable.
        """
        self.scroll_area.setEnabled(enabled)
        self.content_widget.setEnabled(enabled)


class QScrollablePage(QWidget):
    """Scrollable content with a pinned footer area.

    Combines a scrollable body (via QScrollableContainer) with a footer row
    for buttons or status text that stays visible while the body scrolls.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        vertical_policy: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        horizontal_policy: Qt.ScrollBarPolicy = Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        content_margins: tuple[int, int, int, int] = (10, 10, 10, 10),
        footer_margins: tuple[int, int, int, int] = (10, 10, 10, 10),
        footer_alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.body = QScrollableContainer(
            self,
            vertical_policy=vertical_policy,
            horizontal_policy=horizontal_policy,
            margins=content_margins,
        )
        layout.addWidget(self.body)

        self.footer_widget = QWidget(self)
        self.footer_layout = QHBoxLayout(self.footer_widget)
        self.footer_layout.setContentsMargins(*footer_margins)
        self.footer_layout.setAlignment(footer_alignment)
        layout.addWidget(self.footer_widget)

        # Expose body content handles for convenience
        self.content_widget = self.body.content_widget
        self.content_layout = self.body.content_layout

    def add_footer_widget(self, widget: QWidget) -> None:
        """Add a widget to the footer row."""
        self.footer_layout.addWidget(widget)

    def add_footer_spacer(self, stretch: int = 1) -> None:
        """Add stretchable spacer to the footer row."""
        self.footer_layout.addStretch(stretch)

    def set_footer_visible(self, visible: bool) -> None:
        """Toggle footer visibility."""
        self.footer_widget.setVisible(visible)

    def to_dict(self) -> dict[str, Any]:
        """Serialize body scroll state (footer has no state)."""
        return self.body.to_dict()

    def from_dict(self, data: dict[str, Any]) -> None:
        """Restore body scroll state."""
        self.body.from_dict(data)
