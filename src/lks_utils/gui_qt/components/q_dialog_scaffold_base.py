"""Dialog scaffold base: content area + standardized footer button bar."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPushButton, QVBoxLayout, QWidget

from lks_utils.gui_qt.theme.spacing import GAP_SM, PAD_MD
from lks_utils.gui_qt.widgets.q_button_bar_base import QButtonBarBase


class QDialogScaffoldBase(QDialog):
    """QDialog with VBoxLayout, a flexible content area, and a footer QButtonBarBase.

    Usage::

        dlg = QDialogScaffoldBase("Confirm")
        dlg.set_content(my_form_widget)
        ok = dlg.add_footer_button("OK", QDialogButtonBox.ButtonRole.AcceptRole)
        dlg.add_footer_button("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        dlg.exec()
    """

    def __init__(self, title: str, *, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._content_host = QWidget(self)
        self._footer = QButtonBarBase(alignment="right", parent=self)
        self._ok_button: QPushButton | None = None
        self._cancel_button: QPushButton | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(PAD_MD, PAD_MD, PAD_MD, PAD_MD)
        layout.setSpacing(GAP_SM)
        layout.addWidget(self._content_host, stretch=1)
        layout.addWidget(self._footer)

    def set_content(self, widget: QWidget) -> None:
        """Place *widget* inside the content host area."""
        from PySide6.QtWidgets import QVBoxLayout as _VBox

        inner = _VBox(self._content_host)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        widget.setParent(self._content_host)
        inner.addWidget(widget)

    def add_footer_button(
        self,
        text: str,
        role: QDialogButtonBox.ButtonRole,
    ) -> QPushButton:
        """Create a QPushButton, wire it for *role*, and add it to the footer."""
        btn = QPushButton(text, self)
        if role == QDialogButtonBox.ButtonRole.AcceptRole:
            self._ok_button = btn
            btn.clicked.connect(self.accept)
        elif role == QDialogButtonBox.ButtonRole.RejectRole:
            self._cancel_button = btn
            btn.clicked.connect(self.reject)
        self._footer.add_button(btn)
        return btn

    def ok_button(self) -> QPushButton | None:
        """Return the accept-role button if one was added."""
        return self._ok_button

    def cancel_button(self) -> QPushButton | None:
        """Return the reject-role button if one was added."""
        return self._cancel_button

    def footer(self) -> QButtonBarBase:
        """Return the footer QButtonBarBase."""
        return self._footer


__all__ = ["QDialogScaffoldBase"]
