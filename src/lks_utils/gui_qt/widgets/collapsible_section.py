"""Collapsible section widget for PySide6.

A slim clickable ribbon header with arrow toggle and left-aligned title.
Click anywhere on the full-width ribbon to expand/collapse the content area.
"""
from __future__ import annotations

import sys

# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(
            None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass

from typing import Callable

from PySide6.QtCore import (
    QEvent,
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPointF,
    QPropertyAnimation,
    QSize,
    QTimer,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPolygonF, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from shiboken6 import isValid as _is_qt_valid

# ── Visual constants ──────────────────────────────────────────────────────────
_BAR_HEIGHT: int = 22
_ANIM_MS: int = 150  # collapse / expand animation duration (ms)
_ARROW_SIZE: int = 8
_ARROW_LEFT_MARGIN: int = 6
_TEXT_LEFT_GAP: int = 6  # gap between arrow and title text

# Grayscale palette (ribbon stands out from #222 app background)
_BG_NORMAL: str = "#353535"
_BG_HOVER: str = "#404040"
_BG_PRESSED: str = "#2e2e2e"
_BORDER_COLOR: str = "#4a4a4a"
_TEXT_COLOR: str = "#d0d0d0"
_ARROW_COLOR: str = _TEXT_COLOR


class _ContentScrollArea(QScrollArea):
    """Scroll area used as a clip container during collapse/expand animation.

    ``QScrollArea`` with ``setWidgetResizable(True)`` sizes its inner widget
    to ``max(viewport_size, widget.sizeHint())``.  Because our viewport is
    never taller than the widget's natural size, the content widget is never
    squished — Qt simply clips it to the scroll area's visible height.
    Animating *this* widget's ``maximumHeight`` therefore produces a clean
    reveal/hide without triggering relayout on content children.

    ``QAbstractScrollArea.sizeHint()`` returns a hardcoded 256×192 by
    default; we override it to return the inner widget's sizeHint so that
    the parent layout always allocates the correct amount of space.
    """

    def sizeHint(self) -> QSize:
        w = self.widget()
        if w is not None:
            return w.sizeHint()
        return super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)


class _SectionHeader(QWidget):
    """Custom-painted clickable ribbon for ``QCollapsibleSection``."""

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
        self._pressed = False
        self.setFixedHeight(_BAR_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    # ── state updates ────────────────────────────────────────────────

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.update()

    def set_title(self, title: str) -> None:
        self._title = title
        self.update()

    # ── mouse events ─────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pressed = True
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()

    def enterEvent(self, event: object) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event: object) -> None:
        self._hover = False
        self._pressed = False
        self.update()

    # ── painting ─────────────────────────────────────────────────────

    def paintEvent(self, event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Background
        if self._pressed:
            bg = QColor(_BG_PRESSED)
        elif self._hover:
            bg = QColor(_BG_HOVER)
        else:
            bg = QColor(_BG_NORMAL)
        p.fillRect(0, 0, w, h, bg)

        # 1-px bottom border
        p.setPen(QPen(QColor(_BORDER_COLOR), 1))
        p.drawLine(0, h - 1, w, h - 1)

        # Arrow (small filled triangle)
        ax = _ARROW_LEFT_MARGIN
        cy = h / 2.0
        half = _ARROW_SIZE / 2.0

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_ARROW_COLOR))

        if self._expanded:
            # ▼ down-pointing
            pts = [
                QPointF(ax, cy - half * 0.35),
                QPointF(ax + _ARROW_SIZE, cy - half * 0.35),
                QPointF(ax + _ARROW_SIZE / 2.0, cy + half * 0.65),
            ]
        else:
            # ▶ right-pointing
            pts = [
                QPointF(ax + half * 0.15, cy - half),
                QPointF(ax + half * 0.15, cy + half),
                QPointF(ax + _ARROW_SIZE - half * 0.15, cy),
            ]
        p.drawPolygon(QPolygonF(pts))

        # Title text — left-justified, just right of arrow
        p.setPen(QPen(QColor(_TEXT_COLOR), 1))
        font = p.font()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)

        fm = p.fontMetrics()
        text_x = ax + _ARROW_SIZE + _TEXT_LEFT_GAP
        text_y = (h + fm.ascent() - fm.descent()) / 2.0
        p.drawText(int(text_x), int(text_y), self._title)

        p.end()


class QCollapsibleSection(QWidget):
    """A collapsible section with a slim clickable ribbon header.

    The full-width ribbon is clickable — arrow on the left, title
    left-justified next to it.  Expands/collapses the content area below.

    Supports an optional enable checkbox (rendered inside the ribbon row).

    Example::

        section = QCollapsibleSection(title="Advanced Options")
        section.content_layout.addWidget(QLabel("Threshold:"))
        section.toggled.connect(lambda expanded: print(expanded))

        section.expand()
        section.collapse()
        print(section.is_expanded)
    """

    toggled = Signal(bool)
    enabled_changed = Signal(bool)

    def __init__(
        self,
        title: str = "Section",
        *,
        parent: QWidget | None = None,
        has_checkbox: bool = False,
        initially_expanded: bool = True,
        initially_enabled: bool = True,
        fill_vertical: bool = False,
    ) -> None:
        super().__init__(parent)

        self._expanded = initially_expanded
        self._title = title
        self._has_checkbox = has_checkbox
        self._fill_vertical = fill_vertical
        self._cb_enable: QCheckBox | None = None
        self._sync_queued = False

        self._build_ui(initially_enabled)

    def _apply_fill_size_policy(self, expanded: bool) -> None:
        if not self._fill_vertical:
            return
        if expanded:
            v_policy = QSizePolicy.Policy.Expanding
        else:
            v_policy = QSizePolicy.Policy.Maximum
        self.setSizePolicy(QSizePolicy.Policy.Expanding, v_policy)
        if hasattr(self, "_scroll") and _is_qt_valid(self._scroll):
            self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, v_policy)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, initially_enabled: bool) -> None:
        # Horizontal: fill available width.  Vertical: hug content — never
        # accept extra vertical space from a parent layout.
        if not self._fill_vertical:
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        if self._has_checkbox:
            # Checkbox variant: painted header + checkbox in an HBox
            row = QWidget()
            row.setFixedHeight(_BAR_HEIGHT)
            row.setStyleSheet(
                f"background-color: {_BG_NORMAL};"
                f"border-bottom: 1px solid {_BORDER_COLOR};"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 4, 0)
            row_layout.setSpacing(0)

            self._header = _SectionHeader(self._title, self._expanded, self)
            self._header.setFixedHeight(_BAR_HEIGHT)
            self._header.clicked.connect(self._toggle)
            row_layout.addWidget(self._header, stretch=1)

            self._cb_enable = QCheckBox()
            self._cb_enable.setChecked(initially_enabled)
            self._cb_enable.setFixedHeight(_BAR_HEIGHT)
            self._cb_enable.stateChanged.connect(
                lambda state: self.enabled_changed.emit(
                    state == Qt.CheckState.Checked.value
                )
            )
            row_layout.addWidget(self._cb_enable)
            main_layout.addWidget(row)
        else:
            # Standard: full-width painted header
            self._header = _SectionHeader(self._title, self._expanded, self)
            self._header.clicked.connect(self._toggle)
            main_layout.addWidget(self._header)

        # Content area — lives inside a scroll area used as a clip container.
        # The scroll area clips the content without relaying it out, so child
        # widgets don't jostle during animation.
        self.content = QWidget()
        self.content.installEventFilter(self)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 4, 0, 4)

        self._scroll = _ContentScrollArea()
        self._scroll.setWidget(self.content)
        self._scroll.setWidgetResizable(True)  # keeps content width in sync
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        if not self._fill_vertical:
            self._scroll.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        # Transparent viewport so the app background shows through
        self._scroll.viewport().setStyleSheet("background: transparent;")
        main_layout.addWidget(self._scroll)

        self._anim: QParallelAnimationGroup | None = None
        if not self._expanded:
            self._scroll.setMaximumHeight(0)
            self._scroll.setVisible(False)
        self._apply_fill_size_policy(self._expanded)
        self._queue_sync_expanded_geometry()

    # type: ignore[override]
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.content and event.type() in {
            QEvent.Type.LayoutRequest,
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.Polish,
            QEvent.Type.ChildAdded,
            QEvent.Type.ChildRemoved,
        }:
            self._queue_sync_expanded_geometry()
        return super().eventFilter(watched, event)

    def event(self, event: QEvent) -> bool:
        if event.type() in {
            QEvent.Type.LayoutRequest,
            QEvent.Type.Show,
            QEvent.Type.Polish,
            QEvent.Type.PolishRequest,
        }:
            self._queue_sync_expanded_geometry()
        return super().event(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._queue_sync_expanded_geometry()
        # A second queued pass catches late sizeHint updates from nested rows.
        QTimer.singleShot(16, self._queue_sync_expanded_geometry)

    def _queue_sync_expanded_geometry(self) -> None:
        if self._sync_queued:
            return
        self._sync_queued = True

        def _sync_later() -> None:
            self._sync_queued = False
            if not _is_qt_valid(self):
                return
            if not hasattr(self, "content") or not _is_qt_valid(self.content):
                return
            self._sync_expanded_geometry()

        QTimer.singleShot(0, _sync_later)

    def _sync_expanded_geometry(self) -> None:
        if not self._expanded or self._anim is not None:
            return
        if not _is_qt_valid(self.content):
            return
        if not _is_qt_valid(self._scroll):
            return

        # Ensure all nested layouts and widgets are fully processed for accurate sizeHint.
        # This is critical when the section is first expanded/populated with content.

        # Step 1: Ensure the content widget itself is polished
        self.content.ensurePolished()

        # Step 2: Recursively polish all descendants to ensure their size hints are computed
        for child in self.content.findChildren(QWidget):
            child.ensurePolished()
            if child.layout():
                child.layout().activate()

        # Step 3: Activate the content's layout
        if self.content.layout():
            self.content.layout().activate()

        # Calculate the target height. If sizeHint is suspiciously small (likely not fully
        # calculated yet), also check if there's a frame inside and use its sizeHint.
        content_hint = self.content.sizeHint().height()
        content_min_hint = self.content.minimumSizeHint().height()

        # If the primary sizeHints look too small, check for a frame widget inside
        # that might have the actual content dimensions (common pattern in inspector panels)
        if content_hint < 50:  # Suspiciously small
            frames = self.content.findChildren(QFrame)
            for frame in frames:
                frame_hint = frame.sizeHint().height()
                if frame_hint > content_hint:
                    content_hint = frame_hint
                    content_min_hint = max(
                        content_min_hint, frame.minimumSizeHint().height())

        target = max(
            content_hint,
            content_min_hint,
            0,
        )
        self._scroll.setVisible(True)
        self._scroll.setMaximumHeight(16_777_215)
        if self._fill_vertical:
            # In fill mode the parent layout controls the final height.
            # Keeping the section minimum unconstrained allows sibling
            # expanded sections to share space evenly.
            self.setMinimumHeight(0)
        else:
            self.setMinimumHeight(_BAR_HEIGHT + target)
        self.updateGeometry()

    def schedule_geometry_sync(self) -> None:
        """Request a deferred geometry sync for expanded content height."""
        self._queue_sync_expanded_geometry()

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._header.set_expanded(self._expanded)
        self._apply_fill_size_policy(self._expanded)
        self._animate(self._expanded)
        self.toggled.emit(self._expanded)

    def _animate(self, expanding: bool) -> None:
        """Slide the scroll-area clip container open or shut.

        ``content`` is never resized — the scroll area clips it to its
        visible height — so child widgets don't jostle during animation.

        A parallel ``minimumHeight`` animation on the section itself
        forces ancestor layouts (including nested ``QScrollArea`` with
        ``widgetResizable``) to allocate / release space in lockstep.
        """
        if self._anim is not None:
            self._anim.stop()

        if expanding:
            self._scroll.setVisible(True)
            self._scroll.setMaximumHeight(0)
            target = max(
                self.content.sizeHint().height(),
                self.content.minimumSizeHint().height(),
                10,
            )
        else:
            target = 0

        # -- Clip animation (reveal / hide content) --
        anim_clip = QPropertyAnimation(self._scroll, b"maximumHeight", self)
        anim_clip.setDuration(_ANIM_MS)
        anim_clip.setStartValue(0 if expanding else self._scroll.height())
        anim_clip.setEndValue(target)
        anim_clip.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # -- Section minimumHeight animation --
        # Ensures parent layouts allocate space even inside nested
        # QScrollAreas that don't re-evaluate on sizeHint changes alone.
        anim_minh = QPropertyAnimation(self, b"minimumHeight", self)
        anim_minh.setDuration(_ANIM_MS)
        anim_minh.setStartValue(self.minimumHeight())
        anim_minh.setEndValue(
            _BAR_HEIGHT + target if expanding else _BAR_HEIGHT)
        anim_minh.setEasingCurve(QEasingCurve.Type.InOutQuad)

        group = QParallelAnimationGroup(self)
        group.addAnimation(anim_clip)
        group.addAnimation(anim_minh)

        def _finalize_animation() -> None:
            self._anim = None
            self._queue_sync_expanded_geometry()

        if expanding:
            # Remove the cap once fully open so content can grow freely later
            def _on_expand_done() -> None:
                self._scroll.setMaximumHeight(16_777_215)
                _finalize_animation()

            group.finished.connect(_on_expand_done)
        else:
            def _on_collapse_done() -> None:
                self._scroll.setVisible(False)
                self._scroll.setMaximumHeight(16_777_215)
                self.setMinimumHeight(0)
                _finalize_animation()
            group.finished.connect(_on_collapse_done)

        self._anim = group
        group.start()

    def expand(self) -> None:
        if not self._expanded:
            self._toggle()

    def collapse(self) -> None:
        if self._expanded:
            self._toggle()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    @property
    def is_enabled(self) -> bool | None:
        if self._has_checkbox and self._cb_enable is not None:
            return self._cb_enable.isChecked()
        return None

    def set_enabled(self, enabled: bool) -> None:
        if self._has_checkbox and self._cb_enable is not None:
            self._cb_enable.setChecked(enabled)

    def set_on_toggle(self, callback: Callable[[bool], None]) -> None:
        self.toggled.connect(callback)

    def set_expanded(self, expanded: bool) -> None:
        if expanded != self._expanded:
            self._toggle()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, bool | None]:
        state: dict[str, bool | None] = {"expanded": self._expanded}
        if self._has_checkbox and self._cb_enable is not None:
            state["enabled"] = self._cb_enable.isChecked()
        return state

    def from_dict(self, state: dict[str, bool | None]) -> None:
        if "expanded" in state:
            self.set_expanded(state["expanded"])
        if "enabled" in state and self._has_checkbox and self._cb_enable is not None:
            self._cb_enable.setChecked(state["enabled"])


__all__ = ["QCollapsibleSection"]
