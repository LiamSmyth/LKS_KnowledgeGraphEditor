"""Horizontal panel-header strip with title and optional action buttons."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from lks_utils.gui_qt.theme.spacing import GAP_SM, PAD_SM


class QHeaderStripBase(QWidget):
    """Horizontal header strip: title on left, action tool-buttons on right."""

    def __init__(self, title: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title_label = QLabel(title, self)
        self._title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(PAD_SM, PAD_SM, PAD_SM, PAD_SM)
        self._layout.setSpacing(GAP_SM)
        self._layout.addWidget(self._title_label, stretch=1)

    def set_title(self, text: str) -> None:
        """Update the title text."""
        self._title_label.setText(text)

    def text(self) -> str:
        """Compatibility helper mirroring QLabel.text() for legacy callers."""
        return self._title_label.text()

    def title_widget(self) -> QLabel:
        """Return the title QLabel."""
        return self._title_label

    def add_action(self, action: QAction) -> QToolButton:
        """Add a QToolButton wired to *action* and append it to the right side."""
        btn = QToolButton(self)
        btn.setDefaultAction(action)
        self._layout.addWidget(btn)
        return btn


__all__ = ["QHeaderStripBase"]
