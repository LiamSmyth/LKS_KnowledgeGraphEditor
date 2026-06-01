"""Atomic reusable widget primitives for the knowledge module.

Pixmap migration note:
- Node, graph-node, and field-node cards are QWidget-driven and rendered through
    ``CanvasPixmapWidgetItem`` adapters.
- The following items intentionally remain paint-based canvas primitives because
    they represent connector/overlay semantics rather than card content widgets:
    ``QKnowledgePortStubCanvasItem``, ``QKnowledgeGraphLinkCanvasItem``,
    ``_KnowledgeEdgeCanvasItem``, and canvas overlays (for example dot grid).
"""
from __future__ import annotations

from lks_utils.knowledge.ui.widgets.field_node_canvas_item import QKnowledgeFieldNodeCanvasItem
from lks_utils.knowledge.ui.widgets.field_widgets import (
    ClearFieldButton,
    TypeComboBox,
    field_value,
    make_add_action_button,
    make_delete_action_button,
    make_field_label,
    make_pick_action_button,
    make_primitive_field,
    make_simple_button,
    simple_mono_font,
    style_simple_field,
)
from lks_utils.knowledge.ui.widgets.graph_canvas import QKnowledgeGraphCanvasWidget
from lks_utils.knowledge.ui.widgets.graph_node_widget import QKnowledgeGraphNodeWidget
from lks_utils.knowledge.ui.widgets.graph_node_canvas_item import (
    GraphNodeFieldRow,
    QKnowledgeGraphNodeCanvasItem,
)
from lks_utils.knowledge.ui.widgets.graph_link_canvas_item import (
    QKnowledgeGraphLinkCanvasItem,
)
from lks_utils.knowledge.ui.widgets.field_node_widget import QKnowledgeFieldNodeWidget
from lks_utils.knowledge.ui.widgets.node_properties_display_widget import (
    QKnowledgeNodePropertiesDisplayWidget,
)
from lks_utils.knowledge.ui.widgets.link_type_canvas import QKnowledgeLinkTypeCanvasWidget
from lks_utils.knowledge.ui.widgets.knowledge_edit_canvas import QKnowledgeEditCanvasWidget
from lks_utils.knowledge.ui.widgets.validation_badge_row_controller import ValidationBadgeRowController

__all__ = [
    "ClearFieldButton",
    "GraphNodeFieldRow",
    "QKnowledgeGraphCanvasWidget",
    "QKnowledgeGraphLinkCanvasItem",
    "QKnowledgeGraphNodeCanvasItem",
    "QKnowledgeGraphNodeWidget",
    "QKnowledgeFieldNodeCanvasItem",
    "QKnowledgeFieldNodeWidget",
    "QKnowledgeNodePropertiesDisplayWidget",
    "QKnowledgeLinkTypeCanvasWidget",
    "QKnowledgeEditCanvasWidget",
    "ValidationBadgeRowController",
    "TypeComboBox",
    "field_value",
    "make_add_action_button",
    "make_delete_action_button",
    "make_field_label",
    "make_pick_action_button",
    "make_primitive_field",
    "make_simple_button",
    "simple_mono_font",
    "style_simple_field",
]
