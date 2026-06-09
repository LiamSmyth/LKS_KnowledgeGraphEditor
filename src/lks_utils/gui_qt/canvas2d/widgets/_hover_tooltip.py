"""Private hover-tooltip helpers for :class:`Canvas2DWidget`."""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject

HOVER_TOOLTIP_DELAY_MS = 350

class _CanvasHoverTooltipPopup(QWidget):
    """Small mouse-transparent popup used for canvas hover tooltips."""

    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._label = QWidget(self)
        from PySide6.QtWidgets import QLabel, QVBoxLayout

        self._text_label = QLabel(self)
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text_label)

        self._apply_palette_style()
        self.hide()

    def _apply_palette_style(self) -> None:
        palette = self.palette()
        bg = palette.toolTipBase().color().name()
        fg = palette.toolTipText().color().name()
        border = palette.mid().color().name()
        self.setStyleSheet(
            "QWidget {"
            f"background: {bg};"
            f"color: {fg};"
            f"border: 1px solid {border};"
            "border-radius: 0;"
            "}"
        )
        self._text_label.setStyleSheet(
            "QLabel { padding: 4px 6px; border: none; background: transparent; }"
        )

    def show_text(self, global_pos: QPoint, text: str) -> None:
        self._apply_palette_style()
        self._text_label.setText(text)
        self._text_label.adjustSize()
        self.adjustSize()

        anchor = QPoint(global_pos.x() + 16, global_pos.y() + 20)
        screen = QGuiApplication.screenAt(global_pos)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            x = min(anchor.x(), available.right() - self.width())
            y = min(anchor.y(), available.bottom() - self.height())
            anchor = QPoint(max(available.left(), x), max(available.top(), y))
        self.move(anchor)
        self.show()
        self.raise_()


class HoverTooltipMixin:
    """Hover tooltip state and updates for canvas objects."""

    _HOVER_TOOLTIP_DELAY_MS = HOVER_TOOLTIP_DELAY_MS

    def _init_hover_tooltip(self) -> None:
        self._hover_tooltip_popup = _CanvasHoverTooltipPopup()
        self._hover_tooltip_timer = QTimer(self)
        self._hover_tooltip_timer.setSingleShot(True)
        self._hover_tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._hover_tooltip_object: CanvasObject | None = None
        self._hover_tooltip_text: str | None = None
        self._pending_hover_tooltip_object: CanvasObject | None = None
        self._pending_hover_tooltip_text: str | None = None
        self._pending_hover_tooltip_global_pos: QPoint | None = None

    def _clear_hover_tooltip(self) -> None:
        if self._hover_tooltip_text is None and self._pending_hover_tooltip_text is None:
            return
        self._hover_tooltip_timer.stop()
        self._hover_tooltip_popup.hide()
        self._hover_tooltip_object = None
        self._hover_tooltip_text = None
        self._pending_hover_tooltip_object = None
        self._pending_hover_tooltip_text = None
        self._pending_hover_tooltip_global_pos = None

    def _show_hover_tooltip(self) -> None:
        if self._pending_hover_tooltip_text is None or self._pending_hover_tooltip_global_pos is None:
            return
        self._hover_tooltip_popup.show_text(
            self._pending_hover_tooltip_global_pos,
            self._pending_hover_tooltip_text,
        )
        self._hover_tooltip_object = self._pending_hover_tooltip_object
        self._hover_tooltip_text = self._pending_hover_tooltip_text

    def _update_hover_tooltip(
        self,
        screen_pos: tuple[float, float],
        world_pos: tuple[float, float],
    ) -> None:
        hit = self._topmost_hit_object(world_pos)
        tooltip_text: str | None = None
        if hit is not None:
            raw = hit.tooltip_at(world_pos)
            if raw is not None:
                stripped = raw.strip()
                if stripped:
                    tooltip_text = stripped

        if hit is self._hover_tooltip_object and tooltip_text == self._hover_tooltip_text:
            return

        global_pos = self.mapToGlobal(
            QPoint(int(round(screen_pos[0])), int(round(screen_pos[1])))
        )

        if (
            hit is self._pending_hover_tooltip_object
            and tooltip_text == self._pending_hover_tooltip_text
        ):
            self._pending_hover_tooltip_global_pos = global_pos
            return

        if tooltip_text is None:
            self._clear_hover_tooltip()
            return

        self._hover_tooltip_popup.hide()
        self._hover_tooltip_object = None
        self._hover_tooltip_text = None
        self._pending_hover_tooltip_object = hit
        self._pending_hover_tooltip_text = tooltip_text
        self._pending_hover_tooltip_global_pos = global_pos
        self._hover_tooltip_timer.start(self._HOVER_TOOLTIP_DELAY_MS)
