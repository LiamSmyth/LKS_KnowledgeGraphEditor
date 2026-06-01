from __future__ import annotations

from typing import Any

from lks_utils.gui_qt.widgets.q_property_list_display_widget import (
    QPropertyListDisplayWidget,
)

from lks_utils.knowledge.default_theme import (
    FIELD_LABEL_COLOR,
    NODE_LITERAL_VALUE_TEXT,
    NODE_REF_VALUE_TEXT,
    NODE_ROW_SEP,
    NODE_ROWS_PANEL_BG,
    NODE_ROWS_PANEL_BORDER,
    NODE_TEXT_COLOR,
    NODE_TYPE_TEXT,
)


class QKnowledgeNodePropertiesDisplayWidget(QPropertyListDisplayWidget):
    """Knowledge-specific property list with semantic ref/literal formatting."""

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent,
            object_name="knowledge_node_properties",
            label_width_px=64,
            type_width_px=52,
            max_text_lines=3,
            long_text_wrap_trigger_chars=72,
        )
        self.set_style_colors(
            background=NODE_ROWS_PANEL_BG,
            border=NODE_ROWS_PANEL_BORDER,
            row_separator=NODE_ROW_SEP,
            name_text=FIELD_LABEL_COLOR,
            type_text=NODE_TYPE_TEXT,
            value_text=NODE_TEXT_COLOR,
            reference_text=NODE_REF_VALUE_TEXT,
            literal_text=NODE_LITERAL_VALUE_TEXT,
        )

    def _resolve_value_text(self, row: Any) -> str:
        value_text = str(getattr(row, "value", ""))
        value_type = str(getattr(row, "value_type", "")).strip()
        value_kind = str(getattr(row, "value_kind", "plain")).lower()

        def _strip_known_prefix(text: str, tag: str) -> str:
            if text.startswith(f"{tag}:"):
                return text[len(f"{tag}:"):].lstrip()
            if text.startswith(tag):
                return text[len(tag):].lstrip(" :")
            return text

        if value_kind == "reference":
            if value_text.startswith("<Ref>"):
                suffix = _strip_known_prefix(value_text, "<Ref>")
                return f"<Ref>: {suffix}" if suffix else "<Ref>: <missing>"
            return f"<Ref>: {value_text}" if value_text else "<Ref>: <missing>"

        if value_kind != "literal":
            return value_text

        literal_type = value_type if value_type else "value"
        if value_text.startswith("<Literal>"):
            suffix = _strip_known_prefix(value_text, "<Literal>")
            return f"<Literal>: {suffix}" if suffix else f"<Literal>: {literal_type}"
        return f"<Literal>: {value_text}" if value_text else f"<Literal>: {literal_type}"


__all__ = ["QKnowledgeNodePropertiesDisplayWidget"]
