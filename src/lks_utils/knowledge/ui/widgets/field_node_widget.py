from __future__ import annotations

from dataclasses import dataclass

from collections.abc import Sequence

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QVBoxLayout

from lks_utils.gui_qt.widgets.node_header_ribbon_widget import QNodeHeaderRibbonWidget

from lks_utils.knowledge.default_theme import (
    NODE_FILL_COLOR,
    NODE_ROWS_PANEL_BG,
    NODE_ROWS_PANEL_BORDER,
    NODE_STROKE_COLOR,
    NODE_SUBTITLE_TEXT,
    NODE_TEXT_COLOR,
    ROOT_HEADER_BG,
)
from lks_utils.knowledge.ui.widgets.node_properties_display_widget import (
    QKnowledgeNodePropertiesDisplayWidget,
)


@dataclass(frozen=True)
class _FieldDisplayRow:
    label: str
    value_type: str
    value: str
    value_kind: str


class QKnowledgeFieldNodeWidget(QFrame):
    """Canvas-blind field node widget used by pixmap-backed adapters."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._is_root = False
        self.setObjectName("knowledge-field-node")

        self._header = QNodeHeaderRibbonWidget(self)

        self._properties = QKnowledgeNodePropertiesDisplayWidget(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self._properties, stretch=1)

        self._apply_style(QColor(ROOT_HEADER_BG))

    def sync_from_model(
        self,
        *,
        title: str,
        subtitle: str | None,
        is_root: bool,
        selected: bool,
        header_bg_color: str,
        has_validation_errors: bool,
        visible_rows: Sequence[tuple[str, str, str, str]],
        scroll_offset_rows: int,
        max_visible_rows: int,
    ) -> None:
        _ = selected
        self._is_root = is_root
        self._header.set_title_text(title)
        subtitle_text = (subtitle or "").strip()
        if has_validation_errors:
            subtitle_text = f"{subtitle_text} !" if subtitle_text else "!"
        self._header.set_subtitle_text(subtitle_text or None)

        rows = [
            _FieldDisplayRow(
                label=label,
                value_type=value_type,
                value=value,
                value_kind=value_kind,
            )
            for label, value_type, value, value_kind in visible_rows
        ]
        self._properties.sync_from_model(
            rows=rows,
            scroll_offset_rows=scroll_offset_rows,
            max_visible_rows=max_visible_rows,
        )

        self._apply_style(QColor(header_bg_color))

    def _apply_style(self, header_bg: QColor) -> None:
        stroke = QColor(NODE_STROKE_COLOR)
        fill = QColor(NODE_FILL_COLOR)
        text = QColor(NODE_TEXT_COLOR)
        subtitle = QColor(NODE_SUBTITLE_TEXT)
        panel_bg = QColor(NODE_ROWS_PANEL_BG)
        panel_border = QColor(NODE_ROWS_PANEL_BORDER)
        self._header.set_ribbon_background(header_bg)
        self.setStyleSheet(
            "#knowledge-field-node {"
            f"background: {fill.name()};"
            f"border: 1px solid {stroke.name()};"
            "border-radius: 5px;"
            "}"
            "#knowledge-field-node #node_header_ribbon QLabel#title {"
            f"color: {text.name()};"
            "font-size: 12px;"
            "font-weight: 700;"
            "}"
            "#knowledge-field-node #node_header_ribbon QLabel#subtitle {"
            f"color: {subtitle.name()};"
            "font-size: 10px;"
            "font-style: italic;"
            "}"
            "#knowledge-field-node QFrame#knowledge_node_properties {"
            f"background: {panel_bg.name()};"
            f"border: 1px solid {panel_border.name()};"
            "border-radius: 3px;"
            "}"
            "#knowledge-field-node QLabel {"
            f"color: {text.name()};"
            "font-size: 11px;"
            "}"
        )


__all__ = ["QKnowledgeFieldNodeWidget"]
