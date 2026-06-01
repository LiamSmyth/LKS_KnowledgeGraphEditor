"""Capsule tag widget for compact status/capability display."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


class QCapsuleTag(QWidget):
    """A shrink-wrapped capsule with optional status dot and label text.

    The corner rounding is controlled by ``corner_ratio``:
    - ``1.0`` → fully rounded (pill / circular ends)
    - ``0.0`` → square corners
    """

    def __init__(
        self,
        text: str = "",
        *,
        enabled_state: bool = False,
        show_dot: bool = True,
        corner_ratio: float = 1.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._enabled_state = enabled_state
        self._show_dot = show_dot
        self._corner_ratio = max(0.0, min(1.0, corner_ratio))

        self._h_padding = 10
        self._v_padding = 4
        self._dot_size = 8
        self._dot_gap = 6
        self._min_height = 22

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_text(self, text: str) -> None:
        self._text = text
        self.updateGeometry()
        self.update()

    def set_enabled_state(self, enabled_state: bool) -> None:
        self._enabled_state = enabled_state
        self.update()

    def set_corner_ratio(self, corner_ratio: float) -> None:
        self._corner_ratio = max(0.0, min(1.0, corner_ratio))
        self.update()

    def text(self) -> str:
        return self._text

    def enabled_state(self) -> bool:
        return self._enabled_state

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self._text)
        text_h = fm.height()

        width = self._h_padding * 2 + text_w
        if self._show_dot:
            width += self._dot_size + self._dot_gap

        height = max(self._min_height, text_h + self._v_padding * 2)
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(0, 0, -1, -1)
        radius = (rect.height() / 2.0) * self._corner_ratio

        if self._enabled_state:
            bg = QColor("#2f4b34")
            border = QColor("#3f6b47")
            text_color = QColor("#d7e9db")
            dot_color = QColor("#56d36f")
        else:
            bg = QColor("#2f3237")
            border = QColor("#4a4f56")
            text_color = QColor("#a8adb6")
            dot_color = QColor("#6d727a")

        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(rect, radius, radius)

        x = self._h_padding
        if self._show_dot:
            dot_y = (self.height() - self._dot_size) // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(dot_color)
            p.drawEllipse(x, dot_y, self._dot_size, self._dot_size)
            x += self._dot_size + self._dot_gap

        p.setPen(text_color)
        p.setBrush(Qt.BrushStyle.NoBrush)
        fm = p.fontMetrics()
        text_y = (self.height() + fm.ascent() - fm.descent()) // 2
        p.drawText(x, text_y, self._text)

        p.end()
