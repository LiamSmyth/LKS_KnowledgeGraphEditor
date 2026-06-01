"""Presentation-only array display widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QVBoxLayout, QWidget

from lks_utils.gui_qt.components.displays.q_value_display_base import QValueDisplayBase


class QArrayDisplay(QWidget):
    """Read-only array display with one plain label row per item."""

    def __init__(self, values: list[Any] | None = None, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[QValueDisplayBase] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        layout.addWidget(self._body)

        self.set_values(values or [])

    def values(self) -> list[Any]:
        """Return current displayed values."""
        return [row.value() for row in self._rows]

    def set_values(self, values: list[Any]) -> None:
        """Replace displayed rows with new values."""
        while self._rows:
            row = self._rows.pop()
            self._body_layout.removeWidget(row)
            row.deleteLater()
        for value in values:
            row = QValueDisplayBase(value, parent=self)
            self._rows.append(row)
            self._body_layout.addWidget(row)


__all__ = ["QArrayDisplay"]
