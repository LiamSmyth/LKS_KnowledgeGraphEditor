"""Presentation-only dictionary display widget."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.components.displays.q_value_display_base import QValueDisplayBase


class _DictDisplayRow(QWidget):
    """Single read-only dictionary row rendered as key:value labels."""

    def __init__(self, key: Any, value: Any, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key_label = QLabel(str(key), self)
        self.value_display = QValueDisplayBase(value, parent=self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.key_label, 0)
        layout.addWidget(self.value_display, 1)


class QDictDisplay(QWidget):
    """Read-only dictionary display without field chrome."""

    def __init__(self, entries: list[tuple[Any, Any]] | None = None, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_DictDisplayRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._body = QWidget(self)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        layout.addWidget(self._body)

        self.set_entries(entries or [])

    def entries(self) -> list[tuple[Any, Any]]:
        """Return current displayed dictionary entries."""
        return [(row.key_label.text(), row.value_display.value()) for row in self._rows]

    def set_entries(self, entries: list[tuple[Any, Any]]) -> None:
        """Replace displayed entries with new rows."""
        while self._rows:
            row = self._rows.pop()
            self._body_layout.removeWidget(row)
            row.deleteLater()
        for key, value in entries:
            row = _DictDisplayRow(key, value, parent=self)
            self._rows.append(row)
            self._body_layout.addWidget(row)


__all__ = ["QDictDisplay"]
