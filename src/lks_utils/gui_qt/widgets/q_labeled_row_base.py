"""Labeled-row layout base: [label] [editor] [...trailing]."""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from lks_utils.gui_qt.theme.spacing import GAP_SM, PAD_XS, ROW_HEIGHT_COMPACT


class QLabeledRowBase(QWidget):
    """Single-row widget: label on left, editor in middle, optional trailing widgets."""

    def __init__(
        self,
        label: str,
        editor: QWidget,
        *,
        trailing: Sequence[QWidget] = (),
        fixed_height: int = ROW_HEIGHT_COMPACT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label_widget = QLabel(label, self)
        self._editor_widget = editor
        if fixed_height > 0:
            self.setFixedHeight(fixed_height)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(PAD_XS, 0, PAD_XS, 0)
        layout.setSpacing(GAP_SM)
        layout.addWidget(self._label_widget)
        layout.addWidget(self._editor_widget, stretch=1)
        for tw in trailing:
            layout.addWidget(tw)

    def set_label(self, text: str) -> None:
        """Update the label text."""
        self._label_widget.setText(text)

    def label_widget(self) -> QLabel:
        """Return the label QLabel."""
        return self._label_widget

    def editor_widget(self) -> QWidget:
        """Return the editor widget."""
        return self._editor_widget


__all__ = ["QLabeledRowBase"]
