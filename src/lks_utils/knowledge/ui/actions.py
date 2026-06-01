"""Graph-view editor actions and default bindings."""
from __future__ import annotations

from lks_utils.input import (
    Action,
    Binding,
    GestureKind,
    KeyBinding,
    MouseBinding,
    MouseButton,
    get_default_bindings,
)

GRAPH_VIEW_SELECTION_CLEAR_CANVAS = Action(
    id="graph_view.selection.clear_canvas",
    label="Clear Selection From Canvas",
    category="Graph View",
    description="Clear selected graph proxies from the canvas (repository data is preserved).",
    scope="graph_view",
)
KNOWLEDGE_REPO_DELETE_SELECTION = Action(
    id="knowledge.repo.delete_selection",
    label="Delete Selection From Repository",
    category="Knowledge",
    description="Delete selected graph nodes from the repository with reference-safety checks.",
    scope="graph_view",
)
KNOWLEDGE_INSPECTOR_PROMOTE_INLINE_LITERAL = Action(
    id="knowledge.inspector.promote_inline_literal",
    label="Promote Inline Literal",
    category="Knowledge",
    description="Promote an inline literal value to a stand-alone instance node.",
    scope="knowledge.canvas",
)
GRAPH_VIEW_LAYOUT_APPLY_SELECTED = Action(
    id="graph_view.layout.apply_selected",
    label="Apply Layout To Selection",
    category="Graph View",
    description="Apply a layout algorithm to the current graph selection.",
    scope="graph_view",
)
GRAPH_VIEW_DRAG_BEGIN_MULTI_NODE = Action(
    id="graph_view.drag.begin_multi_node",
    label="Begin Multi-Node Drag",
    category="Graph View",
    description="Begin dragging multiple selected nodes as one group.",
    scope="graph_view",
)
GRAPH_VIEW_DRAG_CANCEL = Action(
    id="graph_view.drag.cancel",
    label="Cancel Multi-Node Drag",
    category="Graph View",
    description="Cancel active multi-node drag and restore start positions.",
    scope="graph_view",
)
# Compatibility alias for existing imports.
GRAPH_VIEW_REMOVE_PROXY = GRAPH_VIEW_SELECTION_CLEAR_CANVAS
GRAPH_LINK_CREATE_BEGIN = Action(
    id="graph_view.link_create.begin",
    label="Begin link creation",
    category="Graph View",
    description="Begin graph link creation by dragging from a link-type row.",
    scope="graph_view",
)
GRAPH_LINK_CREATE_SOURCE_CONFIRM = Action(
    id="graph_view.link_create.source_confirm",
    label="Confirm link source",
    category="Graph View",
    description="Confirm a source node while creating a link.",
    scope="graph_view",
)
GRAPH_LINK_CREATE_TARGET_COMMIT = Action(
    id="graph_view.link_create.target_commit",
    label="Commit link target",
    category="Graph View",
    description="Commit the target node and create the link.",
    scope="graph_view",
)
GRAPH_LINK_CREATE_CANCEL = Action(
    id="graph_view.link_create.cancel",
    label="Cancel link creation",
    category="Graph View",
    description="Cancel link creation modal state.",
    scope="graph_view",
)

DEFAULT_BINDINGS: list[tuple[Action, list[Binding]]] = [
    (GRAPH_VIEW_SELECTION_CLEAR_CANVAS, [
     KeyBinding("Delete"), KeyBinding("Del")]),
    (KNOWLEDGE_REPO_DELETE_SELECTION, [
     KeyBinding("Shift+Delete"), KeyBinding("Shift+Del")]),
    (KNOWLEDGE_INSPECTOR_PROMOTE_INLINE_LITERAL, []),
    (GRAPH_VIEW_LAYOUT_APPLY_SELECTED, []),
    (
        GRAPH_VIEW_DRAG_BEGIN_MULTI_NODE,
        [MouseBinding(MouseButton.LEFT, gesture=GestureKind.DRAG)],
    ),
    (GRAPH_VIEW_DRAG_CANCEL, [KeyBinding("Esc")]),
    (
        GRAPH_LINK_CREATE_BEGIN,
        [MouseBinding(MouseButton.LEFT, gesture=GestureKind.DRAG)],
    ),
    (
        GRAPH_LINK_CREATE_SOURCE_CONFIRM,
        [MouseBinding(MouseButton.LEFT, gesture=GestureKind.RELEASE)],
    ),
    (
        GRAPH_LINK_CREATE_TARGET_COMMIT,
        [MouseBinding(MouseButton.LEFT, gesture=GestureKind.PRESS)],
    ),
    (
        GRAPH_LINK_CREATE_CANCEL,
        [
            KeyBinding("Esc"),
            MouseBinding(MouseButton.RIGHT, gesture=GestureKind.PRESS),
        ],
    ),
]


def register_defaults() -> None:
    """Register default graph-view action bindings on global input registry."""
    bindings = get_default_bindings()
    for action, binds in DEFAULT_BINDINGS:
        bindings.register(action, binds)


register_defaults()

__all__ = [
    "DEFAULT_BINDINGS",
    "GRAPH_VIEW_SELECTION_CLEAR_CANVAS",
    "KNOWLEDGE_INSPECTOR_PROMOTE_INLINE_LITERAL",
    "KNOWLEDGE_REPO_DELETE_SELECTION",
    "GRAPH_VIEW_LAYOUT_APPLY_SELECTED",
    "GRAPH_VIEW_DRAG_BEGIN_MULTI_NODE",
    "GRAPH_VIEW_DRAG_CANCEL",
    "GRAPH_VIEW_REMOVE_PROXY",
    "GRAPH_LINK_CREATE_BEGIN",
    "GRAPH_LINK_CREATE_SOURCE_CONFIRM",
    "GRAPH_LINK_CREATE_TARGET_COMMIT",
    "GRAPH_LINK_CREATE_CANCEL",
    "register_defaults",
]
