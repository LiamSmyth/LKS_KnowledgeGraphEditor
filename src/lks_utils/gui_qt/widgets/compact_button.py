"""Compact push button widget for PySide6.

A QPushButton variant with tighter padding around the text, minimal borders,
and a small minimum width. Use wherever space is at a premium (toolbars,
inline controls, library rows).
"""

from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QWidget

# ── Visual constants ──────────────────────────────────────────────────────────
_MIN_WIDTH: int = 40
_H_PAD: int = 6
_V_PAD: int = 2

_STYLE: str = (
    "QPushButton {"
    f"  padding: {_V_PAD}px {_H_PAD}px;"
    f"  min-width: {_MIN_WIDTH}px;"
    "  border: 1px solid #555;"
    "  border-radius: 3px;"
    "  background-color: #3a3a3a;"
    "  color: #d0d0d0;"
    "}"
    "QPushButton:hover {"
    "  background-color: #454545;"
    "  border-color: #777;"
    "}"
    "QPushButton:pressed {"
    "  background-color: #2e2e2e;"
    "}"
    "QPushButton:disabled {"
    "  color: #666;"
    "  border-color: #444;"
    "  background-color: #333;"
    "}"
)


class QCompactButton(QPushButton):
    """QPushButton with tighter padding and minimal borders.

    Shrinks to fit its text content while respecting a small minimum width.
    Styling is self-contained; no external stylesheet needed.

    Example::

        btn = QCompactButton("Save")
        btn.clicked.connect(on_save)
        layout.addWidget(btn)
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(_STYLE)
