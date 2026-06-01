"""QColorSwatchWidget — label + clickable swatch + hex line edit."""
from __future__ import annotations

import re

from lks_utils.theme.color import Color
from lks_utils.gui_qt.theme.color_adapter import to_qcolor, from_qcolor

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame,
    QSizePolicy,
    QColorDialog,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPainter, QColor

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


class _SwatchFrame(QFrame):
    """Clickable coloured square."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setFixedSize(24, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._qcolor = QColor(0, 0, 0)

    def set_qcolor(self, qc: QColor) -> None:
        self._qcolor = qc
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.fillRect(self.rect(), self._qcolor)
        p.end()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.clicked.emit()


class QColorSwatchWidget(QWidget):
    """Compact editor row: ``label  [swatch] #rrggbb``."""

    color_changed = Signal(object)  # Color

    def __init__(
        self,
        label: str,
        color: Color,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._color = color
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(4)

        self._label = QLabel(label)
        self._label.setFixedWidth(180)
        self._label.setToolTip(label)
        layout.addWidget(self._label)

        self._swatch = _SwatchFrame()
        layout.addWidget(self._swatch)

        self._hex_edit = QLineEdit()
        self._hex_edit.setFixedWidth(80)
        self._hex_edit.setMaxLength(7)
        self._hex_edit.setPlaceholderText("#rrggbb")
        layout.addWidget(self._hex_edit)

        layout.addStretch()

        self._swatch.clicked.connect(self._open_color_dialog)
        self._hex_edit.editingFinished.connect(self._on_hex_edited)

        self.set_color(color)

    # ------------------------------------------------------------------

    def color(self) -> Color:
        return self._color

    def set_color(self, color: Color) -> None:
        self._color = color
        qc = to_qcolor(color)
        self._updating = True
        self._swatch.set_qcolor(qc)
        self._hex_edit.setText(f"#{color.to_hex()[1:7]}")
        self._updating = False

    # ------------------------------------------------------------------

    def _open_color_dialog(self) -> None:
        initial = to_qcolor(self._color)
        chosen = QColorDialog.getColor(
            initial,
            self,
            self._label.text(),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if chosen.isValid():
            new_color = from_qcolor(chosen)
            self.set_color(new_color)
            self.color_changed.emit(new_color)

    def _on_hex_edited(self) -> None:
        if self._updating:
            return
        text = self._hex_edit.text().strip()
        m = _HEX_RE.match(text)
        if m:
            hex6 = m.group(1)
            r = int(hex6[0:2], 16)
            g = int(hex6[2:4], 16)
            b = int(hex6[4:6], 16)
            new_color = Color(r=r, g=g, b=b, a=self._color.a)
            self.set_color(new_color)
            self.color_changed.emit(new_color)
        else:
            # Revert to current color on bad input
            self._hex_edit.setText(f"#{self._color.to_hex()[1:7]}")


__all__ = ["QColorSwatchWidget"]
