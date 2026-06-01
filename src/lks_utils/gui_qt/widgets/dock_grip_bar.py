"""Visually distinct title-bar grip widget for dockable panels.

Install via ``dock.setTitleBarWidget(QDockGripBar(title, dock))`` so users
have an immediate visual cue that the panel can be dragged to a new area or
floated.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal, QEvent
from PySide6.QtGui import QPainter, QPalette, QMouseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QStyle,
    QToolButton,
    QWidget,
)


class _GripIndicator(QWidget):
    """Paints a 2 × 3 dot grid to signal that the bar is draggable."""

    _COLS: int = 2
    _ROWS: int = 3
    _DOT_RADIUS: float = 1.5
    _SPACING: int = 5

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        w = (self._COLS - 1) * self._SPACING + 10
        h = (self._ROWS - 1) * self._SPACING + 8
        self.setFixedSize(w, h)

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(QPalette.ColorRole.Mid)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        total_w = (self._COLS - 1) * self._SPACING
        total_h = (self._ROWS - 1) * self._SPACING
        x0 = (self.width() - total_w) / 2.0
        y0 = (self.height() - total_h) / 2.0
        for row in range(self._ROWS):
            for col in range(self._COLS):
                cx = x0 + col * self._SPACING
                cy = y0 + row * self._SPACING
                painter.drawEllipse(
                    QPointF(cx, cy),
                    self._DOT_RADIUS,
                    self._DOT_RADIUS,
                )


class QDockGripBar(QWidget):
    """Custom title-bar widget installed on managed ``QDockWidget`` instances.

    Renders a 2 × 3 dot-grid grip indicator on the left (visual affordance for
    dragging), the dock title in the centre, and float / close buttons on the
    right.  The bar background uses ``QPalette.Dark`` so it is visually
    distinct from the dock panel content area.

    Usage::

        bar = QDockGripBar("Inspector", dock)
        dock.setTitleBarWidget(bar)

    The bar stays in sync with the dock's floating state automatically.
    Call :meth:`set_title` when renaming the dock after construction.
    """

    _BAR_HEIGHT: int = 24

    grip_mouse_pressed = Signal(QPoint)
    grip_mouse_moved = Signal(QPoint)
    grip_mouse_released = Signal(QPoint)

    def __init__(self, title: str, dock: QDockWidget) -> None:
        super().__init__(dock)
        self._dock = dock
        self._drag_press_active = False
        self.setFixedHeight(self._BAR_HEIGHT)
        self.setAutoFillBackground(False)  # custom paintEvent handles bg

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(4)

        self._grip = _GripIndicator(self)
        self._grip.setMouseTracking(True)
        self._grip.installEventFilter(self)
        layout.addWidget(self._grip)

        self._title_lbl = QLabel(title, self)
        font = self._title_lbl.font()
        font.setBold(True)
        self._title_lbl.setFont(font)
        layout.addWidget(self._title_lbl, 1)

        style = self.style()
        features = dock.features()

        if features & QDockWidget.DockWidgetFeature.DockWidgetFloatable:
            self._float_btn: QToolButton | None = QToolButton(self)
            self._float_btn.setFixedSize(16, 16)
            self._float_btn.clicked.connect(self._toggle_float)
            layout.addWidget(self._float_btn)
        else:
            self._float_btn = None

        if features & QDockWidget.DockWidgetFeature.DockWidgetClosable:
            self._close_btn: QToolButton | None = QToolButton(self)
            self._close_btn.setFixedSize(16, 16)
            self._close_btn.setIcon(
                style.standardIcon(
                    QStyle.StandardPixmap.SP_TitleBarCloseButton)
            )
            self._close_btn.setToolTip("Close")
            self._close_btn.clicked.connect(dock.close)
            layout.addWidget(self._close_btn)
        else:
            self._close_btn = None

        dock.topLevelChanged.connect(self._on_top_level_changed)
        self._on_top_level_changed(dock.isFloating())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_title(self, title: str) -> None:
        """Update the displayed title text."""
        self._title_lbl.setText(title)

    def grip_widget(self) -> QWidget:
        """Return the grip widget used for grip-only interaction wiring."""
        return self._grip

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: ANN001
        """Fill with the Dark palette role so the bar reads as a header."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(
            QPalette.ColorRole.Dark))

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:
        if watched is not self._grip:
            return super().eventFilter(watched, event)

        event_type = event.type()
        if not isinstance(event, QMouseEvent):
            return super().eventFilter(watched, event)

        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.grip_mouse_pressed.emit(event.globalPosition().toPoint())
            return False
        if event_type == QEvent.Type.MouseMove:
            self.grip_mouse_moved.emit(event.globalPosition().toPoint())
            return False
        if event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            self.grip_mouse_released.emit(event.globalPosition().toPoint())
            return False
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        target = self.childAt(event.position().toPoint())
        if isinstance(target, QToolButton):
            return
        self._drag_press_active = True
        self.grip_mouse_pressed.emit(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if not self._drag_press_active:
            return
        self.grip_mouse_moved.emit(event.globalPosition().toPoint())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._drag_press_active:
            self.grip_mouse_released.emit(event.globalPosition().toPoint())
        self._drag_press_active = False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _toggle_float(self) -> None:
        self._dock.setFloating(not self._dock.isFloating())

    def _on_top_level_changed(self, floating: bool) -> None:
        if self._float_btn is None:
            return
        style = self.style()
        if floating:
            icon = style.standardIcon(
                QStyle.StandardPixmap.SP_TitleBarNormalButton)
            self._float_btn.setToolTip("Re-dock")
        else:
            icon = style.standardIcon(
                QStyle.StandardPixmap.SP_TitleBarMaxButton)
            self._float_btn.setToolTip("Float")
        self._float_btn.setIcon(icon)
