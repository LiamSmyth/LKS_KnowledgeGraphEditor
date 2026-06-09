"""Qt pixel-space card shell for pixmap-backed canvas nodes."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from lks_utils.gui_qt.widgets.node_header_ribbon_widget import QNodeHeaderRibbonWidget


class QCanvasNodeCardWidget(QFrame):
    """Full node card rendered via ``QWidget.render`` → canvas pixmap.

    Header title/subtitle, separator, border, and body text/layout are all
    Qt-owned. The canvas must not draw text or complex chrome in GL for this
    object — only blit the resulting pixmap.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("canvas_node_card")

        self._header = QNodeHeaderRibbonWidget(self)
        self._body = QLabel(self)
        self._body.setObjectName("body")
        self._body.setWordWrap(True)
        self._body.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._body, stretch=1)

    @property
    def header(self) -> QNodeHeaderRibbonWidget:
        return self._header

    @property
    def body(self) -> QLabel:
        return self._body

    def set_body_widget(self, widget: QWidget) -> None:
        """Replace the default body label with a custom body widget."""
        layout = self.layout()
        if layout is None:
            return
        layout.removeWidget(self._body)
        self._body.hide()
        self._body.setParent(None)
        layout.addWidget(widget, stretch=1)

    def apply_appearance(
        self,
        *,
        title: str,
        subtitle: str | None,
        header_bg: QColor,
        stroke: QColor,
        fill: QColor,
        title_color: QColor,
        subtitle_color: QColor,
        separator_color: QColor,
        body_text: str = "",
    ) -> None:
        self._header.set_title_text(title)
        self._header.set_subtitle_text(subtitle)
        self._header.set_ribbon_style(
            background=header_bg,
            separator=separator_color,
            title_color=title_color,
            subtitle_color=subtitle_color,
        )
        self._body.setText(body_text)
        stroke_name = stroke.name()
        fill_name = fill.name()
        title_name = title_color.name()
        subtitle_name = subtitle_color.name()
        self.setStyleSheet(
            "#canvas_node_card {"
            f"background: {fill_name};"
            f"border: 1px solid {stroke_name};"
            "border-radius: 5px;"
            "}"
            "#canvas_node_card QLabel#body {"
            f"color: {title_name};"
            "font-size: 11px;"
            "padding: 8px;"
            "background: transparent;"
            "border: none;"
            "}"
            "#canvas_node_card #node_header_ribbon QLabel#title {"
            f"color: {title_name};"
            "font-size: 12px;"
            "font-weight: 700;"
            "background: transparent;"
            "}"
            "#canvas_node_card #node_header_ribbon QLabel#subtitle {"
            f"color: {subtitle_name};"
            "font-size: 10px;"
            "font-style: italic;"
            "background: transparent;"
            "}"
        )


__all__ = ["QCanvasNodeCardWidget"]
