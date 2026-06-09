"""Factory for knowledge graph node canvas objects with stock capabilities."""
from __future__ import annotations

from collections.abc import Callable

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities.capability_resize_rect import (
    ResizeRectCapability,
)
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities.capability_selectable import (
    SelectableCapability,
)
from lks_utils.knowledge.ui.widgets._placement import GraphNodeRenderModel
from lks_utils.knowledge.ui.widgets.capability_graph_node_drag import GraphNodeDragCapability
from lks_utils.knowledge.ui.widgets.graph_node_canvas_object import QKnowledgeGraphNodeCanvasObject


def make_graph_node_object(
    *,
    node_id: str,
    model: GraphNodeRenderModel,
    x: float,
    y: float,
    on_moved: Callable[[str], None] | None = None,
    on_clear: Callable[[str], None] | None = None,
    linked_sync: Callable[[tuple[float, float]], None] | None = None,
) -> QKnowledgeGraphNodeCanvasObject:
    """Build a graph node canvas object with explicit capability attachments."""
    node = QKnowledgeGraphNodeCanvasObject(
        node_id=node_id,
        title=model.title,
        subtitle=model.subtitle,
        x=x,
        y=y,
        width=model.width,
        height=model.height,
        rows=model.rows,
        max_visible_rows=model.max_visible_rows,
        header_bg_color=model.header_bg,
        on_clear=on_clear,
        on_moved=on_moved,
    )
    node.draggable = False
    node.attach(GraphNodeDragCapability(linked_sync=linked_sync))
    node.attach(ResizeRectCapability(min_size=(120, 64)))
    node.attach(SelectableCapability())
    return node


__all__ = ["make_graph_node_object"]
