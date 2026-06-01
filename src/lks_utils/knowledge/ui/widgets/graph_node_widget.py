from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QSizePolicy

from lks_utils.gui_qt.widgets.node_header_ribbon_widget import QNodeHeaderRibbonWidget
from lks_utils.knowledge.default_theme import (
    NODE_FILL_COLOR,
    NODE_HEADER_BG,
    NODE_SELECTED_STROKE_COLOR,
    NODE_STROKE_COLOR,
    NODE_SUBTITLE_TEXT,
    NODE_TEXT_COLOR,
    NODE_ROWS_PANEL_BG,
    VALIDATION_ERROR_STRIPE,
    VALIDATION_ERROR_TEXT,
    VALIDATION_WARNING_LABEL,
)
from lks_utils.knowledge.ui.widgets.field_widgets import make_square_svg_icon
from lks_utils.knowledge.ui.widgets.node_properties_display_widget import (
    QKnowledgeNodePropertiesDisplayWidget,
)


class _QClipboardTooltipLabel(QLabel):
    """Badge label that copies its tooltip text to the clipboard on click."""

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        super().mousePressEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        tooltip = (self.toolTip() or "").strip()
        if not tooltip:
            return
        QApplication.clipboard().setText(tooltip)


class QKnowledgeGraphNodeWidget(QFrame):
    """Canvas-blind graph node widget used by pixmap-backed adapters."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._clear_enabled = False

        self.setObjectName("knowledge-graph-node")

        self._header = QNodeHeaderRibbonWidget(self)
        self._clear_button = self._header.add_action_icon_button(
            icon=make_square_svg_icon("kwb_btn_clear.svg"),
            tooltip="Remove from graph",
            on_clicked=self._emit_clear,
            edge_px=12,
            show_border=False,
            show_backdrop=False,
        )
        self._validation_badge = _QClipboardTooltipLabel(self._header)
        self._validation_badge.setObjectName("validation_summary_badge")
        self._validation_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter,
        )
        self._validation_badge.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._validation_badge.hide()
        self._header.insert_action_widget(0, self._validation_badge)
        self._properties = QKnowledgeNodePropertiesDisplayWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._properties, stretch=1)

        self._apply_style(QColor(NODE_HEADER_BG))

    def sync_from_model(
        self,
        *,
        title: str,
        subtitle: str | None,
        rows: Sequence[Any],
        selected: bool,
        active_selected: bool,
        header_bg_color: str,
        scroll_offset_rows: int,
        max_visible_rows: int,
        clear_enabled: bool,
        validation_badge_text: str | None = None,
        validation_badge_tooltip: str | None = None,
        validation_badge_kind: str | None = None,
    ) -> None:
        self._header.set_title_text(title)
        self._header.set_subtitle_text(subtitle)
        _ = (selected, active_selected)
        self._clear_enabled = bool(clear_enabled)
        self._update_validation_badge(
            text=validation_badge_text,
            tooltip=validation_badge_tooltip,
            kind=validation_badge_kind,
        )
        self._properties.sync_from_model(
            rows=rows,
            scroll_offset_rows=scroll_offset_rows,
            max_visible_rows=max_visible_rows,
        )

        self._apply_style(QColor(header_bg_color))

    def set_on_clear(self, callback: Callable[[], None] | None) -> None:
        self._on_clear = callback

    def _update_validation_badge(
        self,
        *,
        text: str | None,
        tooltip: str | None,
        kind: str | None,
    ) -> None:
        cleaned_text = (text or "").strip()
        cleaned_tooltip = (tooltip or "").strip()
        if not cleaned_text:
            self._validation_badge.clear()
            self._validation_badge.hide()
            self._validation_badge.setToolTip("")
            self.setToolTip("")
            return

        border_color = VALIDATION_WARNING_LABEL
        text_color = VALIDATION_WARNING_LABEL
        if kind == "error":
            border_color = VALIDATION_ERROR_STRIPE
            text_color = VALIDATION_ERROR_TEXT
        elif kind == "mixed":
            border_color = VALIDATION_ERROR_STRIPE
            text_color = VALIDATION_ERROR_TEXT

        self._validation_badge.setText(cleaned_text)
        self._validation_badge.setToolTip(cleaned_tooltip)
        self._validation_badge.setVisible(True)
        self.setToolTip(cleaned_tooltip)
        self._validation_badge.setStyleSheet(
            "QLabel#validation_summary_badge {"
            f"background: {NODE_ROWS_PANEL_BG};"
            f"color: {text_color};"
            f"border: 1px solid {border_color};"
            "border-radius: 7px;"
            "padding: 0px 5px;"
            "font-size: 9px;"
            "font-weight: 700;"
            "}"
        )

    def _emit_clear(self) -> None:
        callback = getattr(self, "_on_clear", None)
        if callable(callback) and self._clear_enabled:
            callback()

    def _apply_style(self, header_bg: QColor) -> None:
        stroke_color = QColor(NODE_STROKE_COLOR)
        fill = QColor(NODE_FILL_COLOR)
        text = QColor(NODE_TEXT_COLOR)
        subtitle = QColor(NODE_SUBTITLE_TEXT)
        self._header.set_ribbon_background(header_bg)
        self.setStyleSheet(
            "#knowledge-graph-node {"
            f"background: {fill.name()};"
            f"border: 1px solid {stroke_color.name()};"
            "border-radius: 5px;"
            "}"
            "#knowledge-graph-node #node_header_ribbon QLabel#title {"
            f"color: {text.name()};"
            "font-size: 12px;"
            "font-weight: 700;"
            "}"
            "#knowledge-graph-node #node_header_ribbon QLabel#subtitle {"
            f"color: {subtitle.name()};"
            "font-size: 10px;"
            "font-style: italic;"
            "}"
            "#knowledge-graph-node QLabel {"
            f"color: {text.name()};"
            "font-size: 11px;"
            "}"
        )


__all__ = ["QKnowledgeGraphNodeWidget"]
