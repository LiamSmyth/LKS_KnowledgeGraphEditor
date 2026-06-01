"""Horizontal button bar with configurable alignment."""
from __future__ import annotations

from typing import Literal

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QToolButton, QWidget

from lks_utils.gui_qt.theme.spacing import GAP_SM, PAD_XS


class QButtonBarBase(QWidget):
    """Horizontal row of buttons with configurable alignment.

    alignment:
      ``'left'``   — buttons flush-left, stretch on the right.
      ``'center'`` — stretch on both sides.
      ``'right'``  — stretch on the left, buttons flush-right (default).
    """

    def __init__(
        self,
        *,
        alignment: Literal["left", "center", "right"] = "right",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._alignment = alignment
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(PAD_XS, PAD_XS, PAD_XS, PAD_XS)
        self._layout.setSpacing(GAP_SM)
        # Leading stretch for 'right' or 'center' pushes buttons rightward / inward
        if alignment in ("right", "center"):
            self._layout.addStretch()
        # Trailing stretch for 'center' — buttons are inserted between the two stretches
        if alignment == "center":
            self._layout.addStretch()

    def add_button(self, button: QPushButton | QToolButton) -> None:
        """Append *button* respecting the chosen alignment."""
        if self._alignment == "right":
            # Append after the leading stretch so buttons sit flush-right
            self._layout.addWidget(button)
        elif self._alignment == "center":
            # Insert before the trailing stretch so buttons sit centered
            self._layout.insertWidget(self._layout.count() - 1, button)
        else:
            self._layout.addWidget(button)

    def add_stretch(self) -> None:
        """Explicitly insert a stretch spacer."""
        self._layout.addStretch()


__all__ = ["QButtonBarBase"]
