"""Reusable top-ribbon header for node-like widgets."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QSizePolicy, QWidget

from lks_utils.gui_qt.widgets.elided_label import QElidedLabel
from lks_utils.gui_qt.widgets.square_icon_button import QSquareIconButton


class QNodeHeaderRibbonWidget(QFrame):
    """Header ribbon with left title, right subtitle, and optional action region."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("node_header_ribbon")

        self._title_label = QElidedLabel(parent=self)
        self._title_label.setObjectName("title")
        self._title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self._subtitle_label = QElidedLabel(
            parent=self,
            elide_mode=Qt.TextElideMode.ElideLeft,
        )
        self._subtitle_label.setObjectName("subtitle")
        self._subtitle_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self._subtitle_label.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Preferred,
        )

        self._actions_host = QWidget(self)
        self._actions_host.setObjectName("actions")
        self._actions_layout = QHBoxLayout(self._actions_host)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(3)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 6, 3)
        layout.setSpacing(6)
        layout.addWidget(self._title_label, stretch=1)
        layout.addWidget(self._subtitle_label, stretch=0)
        layout.addWidget(self._actions_host, stretch=0)

    def set_title_text(self, text: str) -> None:
        self._title_label.setText(text)

    def set_subtitle_text(self, text: str | None) -> None:
        value = text or ""
        self._subtitle_label.setText(value)
        self._subtitle_label.setVisible(bool(value))

    def set_ribbon_background(self, color: QColor) -> None:
        self.set_ribbon_style(background=color)

    def set_ribbon_style(
        self,
        *,
        background: QColor,
        separator: QColor | None = None,
        title_color: QColor | None = None,
        subtitle_color: QColor | None = None,
    ) -> None:
        separator_css = (
            f"border-bottom: 1px solid {separator.name()};"
            if separator is not None
            else ""
        )
        title_css = (
            f"color: {title_color.name()};"
            if title_color is not None
            else ""
        )
        subtitle_css = (
            f"color: {subtitle_color.name()};"
            if subtitle_color is not None
            else ""
        )
        self.setStyleSheet(
            "#node_header_ribbon {"
            f"background: {background.name()};"
            "border: none;"
            "border-top-left-radius: 5px;"
            "border-top-right-radius: 5px;"
            f"{separator_css}"
            "}"
            + (
                f"#node_header_ribbon QLabel#title {{{title_css}}}"
                if title_css
                else ""
            )
            + (
                f"#node_header_ribbon QLabel#subtitle {{{subtitle_css}}}"
                if subtitle_css
                else ""
            )
        )

    def clear_action_widgets(self) -> None:
        while self._actions_layout.count() > 0:
            item = self._actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def insert_action_widget(self, index: int, widget: QWidget) -> QWidget:
        self._actions_layout.insertWidget(max(0, int(index)), widget)
        return widget

    def add_action_widget(self, widget: QWidget) -> QWidget:
        self._actions_layout.addWidget(widget)
        return widget

    def add_action_button(
        self,
        *,
        text: str,
        tooltip: str,
        on_clicked: Callable[[], None] | None = None,
        edge_px: int = 14,
    ) -> QPushButton:
        button = QPushButton(text, self._actions_host)
        button.setObjectName("header_action_button")
        button.setFixedSize(edge_px, edge_px)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolTip(tooltip)
        button.setStyleSheet(
            "QPushButton#header_action_button {"
            "padding: 0;"
            "margin: 0;"
            "font-size: 10px;"
            "font-weight: 700;"
            "border: 1px solid rgba(200,200,200,0.55);"
            "border-radius: 2px;"
            "background: rgba(0,0,0,0.15);"
            "color: #d7e6ff;"
            "}"
            "QPushButton#header_action_button:hover {"
            "background: rgba(0,0,0,0.35);"
            "}"
        )
        if on_clicked is not None:
            button.clicked.connect(on_clicked)
        self._actions_layout.addWidget(button)
        return button

    def add_action_icon_button(
        self,
        *,
        icon: QIcon,
        tooltip: str,
        on_clicked: Callable[[], None] | None = None,
        edge_px: int = 14,
        show_border: bool = False,
        show_backdrop: bool = False,
    ) -> QSquareIconButton:
        button = QSquareIconButton(
            edge_px,
            icon=icon,
            tooltip=tooltip,
            show_border=show_border,
            show_backdrop=show_backdrop,
            parent=self._actions_host,
        )
        button.setObjectName("header_action_icon_button")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if on_clicked is not None:
            button.clicked.connect(on_clicked)
        self._actions_layout.addWidget(button)
        return button


__all__ = ["QNodeHeaderRibbonWidget"]
