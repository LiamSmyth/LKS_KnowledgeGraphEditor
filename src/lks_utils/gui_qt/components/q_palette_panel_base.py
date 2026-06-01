"""Title + content panel base for palette-style side panels."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme.spacing import GAP_SM, PAD_SM
from lks_utils.gui_qt.widgets.q_header_strip_base import QHeaderStripBase


class QPalettePanelBase(QWidget):
    """Vertical panel: QHeaderStripBase title at top, scrollable content widget below.

    Usage::

        panel = QPalettePanelBase("My Panel")
        panel.set_content(my_list_widget)
    """

    def __init__(
        self,
        title: str,
        *,
        content: QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._header = QHeaderStripBase(title, parent=self)
        self._content_host = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAD_SM, PAD_SM, PAD_SM, PAD_SM)
        layout.setSpacing(GAP_SM)
        layout.addWidget(self._header)
        layout.addWidget(self._content_host, stretch=1)
        if content is not None:
            self.set_content(content)

    def set_title(self, text: str) -> None:
        """Update the panel title."""
        self._header.set_title(text)

    def set_content(self, widget: QWidget) -> None:
        """Replace the current content widget."""
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)  # type: ignore[arg-type]
        widget.setParent(self._content_host)
        self._content_layout.addWidget(widget, stretch=1)

    def title_label(self) -> QLabel:
        """Return the title QLabel (convenience accessor)."""
        return self._header.title_widget()

    def header_strip(self) -> QHeaderStripBase:
        """Return the header strip widget."""
        return self._header


__all__ = ["QPalettePanelBase"]
