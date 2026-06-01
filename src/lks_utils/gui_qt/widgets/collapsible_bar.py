"""Collapsible bar widget for PySide6.

A slim horizontal bar with a small arrow toggle and centered title.
Designed for compact lists of collapsible fields (e.g., mapping editors).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lks_utils.gui_qt.theme import COLORS

# Arrow size (side length of the square bounding box)
_ARROW_SIZE: int = 10
# Bar height
_BAR_HEIGHT: int = 24


class _BarHeader(QWidget):
    """Clickable header bar with arrow indicator and centered text."""

    clicked = Signal()

    def __init__(
        self,
        title: str,
        expanded: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._expanded = expanded
        self._hover = False
        self.setFixedHeight(_BAR_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)

    # -- state -----------------------------------------------------------

    def set_expanded(self, expanded: bool) -> None:
        """Update the arrow direction."""
        self._expanded = expanded
        self.update()

    def set_title(self, title: str) -> None:
        """Update displayed title."""
        self._title = title
        self.update()

    # -- events ----------------------------------------------------------

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        """Emit clicked on mouse press."""
        self.clicked.emit()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self._hover = False
        self.update()

    # -- painting --------------------------------------------------------

    def paintEvent(self, event: object) -> None:  # noqa: N802
        """Draw the bar: background, arrow, centered text."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Background — barely distinguishable from main bg (#222222)
        bg = QColor(COLORS["bg"]).lighter(115)  # ~#282828
        if self._hover:
            bg = bg.lighter(110)
        painter.fillRect(0, 0, w, h, bg)

        # Subtle outline around the entire bar
        outline = QColor(COLORS["border"])
        outline.setAlpha(80)  # very faint
        painter.setPen(QPen(outline, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(0, 0, w - 1, h - 1)

        # Arrow (small filled triangle)
        arrow_x = 8
        arrow_cy = h / 2.0
        half = _ARROW_SIZE / 2.0

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(COLORS["light"]))

        if self._expanded:
            # Down-pointing triangle  ▼
            points = [
                QPointF(arrow_x, arrow_cy - half * 0.35),
                QPointF(arrow_x + _ARROW_SIZE, arrow_cy - half * 0.35),
                QPointF(arrow_x + _ARROW_SIZE / 2.0, arrow_cy + half * 0.65),
            ]
        else:
            # Right-pointing triangle  ▶
            points = [
                QPointF(arrow_x + half * 0.2, arrow_cy - half),
                QPointF(arrow_x + half * 0.2, arrow_cy + half),
                QPointF(arrow_x + _ARROW_SIZE - half * 0.2, arrow_cy),
            ]

        painter.drawPolygon(QPolygonF(points))

        # Centered text
        painter.setPen(QPen(QColor(COLORS["fg"]), 1))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(self._title)
        text_x = (w - text_w) / 2.0
        text_y = (h + fm.ascent() - fm.descent()) / 2.0
        painter.drawText(int(text_x), int(text_y), self._title)

        painter.end()


class QCollapsibleBar(QWidget):
    """A slim collapsible bar with arrow toggle and centered title.

    Visually distinct from QCollapsibleSection: renders as a thin
    horizontal strip with a small filled-triangle arrow at the left
    and the title text centered in the bar.

    Example::

        bar = QCollapsibleBar(parent, title="Date", initially_expanded=False)
        bar.content_layout.addWidget(QLabel("Some content here"))

        bar.toggled.connect(lambda expanded: print(expanded))

        # Programmatic control
        bar.expand()
        bar.collapse()
    """

    # Signal emitted when section expands/collapses (True = expanded)
    toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "Section",
        initially_expanded: bool = True,
    ) -> None:
        """Initialize collapsible bar.

        Args:
            parent: Parent widget.
            title: Title shown centered in the bar.
            initially_expanded: Whether content is visible on creation.
        """
        super().__init__(parent)
        self._expanded = initially_expanded
        self._title = title
        self._build_ui()

    def _build_ui(self) -> None:
        """Construct header bar + collapsible content area."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        self._header = _BarHeader(self._title, self._expanded, self)
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        # Content area — subtle border + slightly darker background
        self.content = QWidget()
        bg_darker = QColor(COLORS["bg"]).darker(115).name()
        border_color = QColor(COLORS["border"])
        border_color.setAlpha(80)
        # Qt stylesheets don't support alpha on border, so approximate
        border_hex = QColor(
            border_color.red(), border_color.green(), border_color.blue()
        ).darker(110).name()
        self.content.setStyleSheet(
            f"QWidget#_collapsible_bar_content {{"
            f"  background-color: {bg_darker};"
            f"  border: 1px solid {border_hex};"
            f"  border-top: none;"
            f"}}"
        )
        self.content.setObjectName("_collapsible_bar_content")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.content)

        self.content.setVisible(self._expanded)

    # -- public API ------------------------------------------------------

    def _toggle(self) -> None:
        """Toggle expanded/collapsed state."""
        self._expanded = not self._expanded
        self._header.set_expanded(self._expanded)
        self.content.setVisible(self._expanded)
        self.toggled.emit(self._expanded)

    def expand(self) -> None:
        """Expand the section."""
        if not self._expanded:
            self._toggle()

    def collapse(self) -> None:
        """Collapse the section."""
        if self._expanded:
            self._toggle()

    @property
    def is_expanded(self) -> bool:
        """Return whether the section is currently expanded."""
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        """Set expanded/collapsed state programmatically.

        Args:
            expanded: True to expand, False to collapse.
        """
        if expanded != self._expanded:
            self._toggle()

    def set_title(self, title: str) -> None:
        """Update the bar title.

        Args:
            title: New title text.
        """
        self._title = title
        self._header.set_title(title)

    def to_dict(self) -> dict[str, bool]:
        """Serialize state for persistence.

        Returns:
            Dict with ``expanded`` key.
        """
        return {"expanded": self._expanded}

    def from_dict(self, state: dict[str, bool]) -> None:
        """Restore state from dict.

        Args:
            state: Dict with ``expanded`` key.
        """
        if "expanded" in state:
            self.set_expanded(state["expanded"])


__all__ = ["QCollapsibleBar"]
