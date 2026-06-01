"""Input actions and defaults for the knowledge editor surfaces."""
from __future__ import annotations

from lks_utils.input import (
    Action,
    Binding,
    GestureKind,
    InputBindings,
    KeyBinding,
    Modifier,
    MouseBinding,
    MouseButton,
    get_default_bindings,
)

REPO_NEW = Action(
    id="knowledge.repo.new",
    label="New repository",
    category="Knowledge",
    description="Create a new repository at a selected folder.",
    scope="knowledge",
)
REPO_OPEN = Action(
    id="knowledge.repo.open",
    label="Open repository",
    category="Knowledge",
    description="Open an existing repository folder.",
    scope="knowledge",
)
REPO_SAVE_AS = Action(
    id="knowledge.repo.save_as",
    label="Save repository as",
    category="Knowledge",
    description="Save repository to a new folder.",
    scope="knowledge",
)
PALETTE_SPAWN_SEARCH = Action(
    id="knowledge.palette.spawn_search",
    label="Spawn search popup",
    category="Knowledge",
    description="Open the decomposition canvas search popup.",
    scope="knowledge.canvas",
)
FIELD_COLLAPSE_RECURSIVE = Action(
    id="knowledge.field.collapse_recursive",
    label="Toggle recursive collapse",
    category="Knowledge",
    description="Alt-click to recursively expand/collapse a field tree.",
    scope="knowledge.canvas",
)
FIELD_PICK_REF = Action(
    id="knowledge.field.pick_ref",
    label="Pick reference",
    category="Knowledge",
    description="Open the ref picker for a reference property.",
    scope="knowledge.canvas",
)
FIELD_CLEAR_REF = Action(
    id="knowledge.field.clear_ref",
    label="Clear reference",
    category="Knowledge",
    description="Clear an existing reference property value.",
    scope="knowledge.canvas",
)
ADD_TYPE = Action(
    id="knowledge.type.add",
    label="Add type",
    category="Knowledge",
    description="Open the Add Type dialog.",
    scope="knowledge",
)
ADD_INSTANCE = Action(
    id="knowledge.instance.add",
    label="Add instance",
    category="Knowledge",
    description="Open the Add Instance dialog.",
    scope="knowledge",
)
ADD_SLOT = Action(
    id="knowledge.type.add_slot",
    label="Add slot / property",
    category="Knowledge",
    description="Open the Add Slot dialog for the current type.",
    scope="knowledge",
)
SWITCH_TO_TYPES_TAB = Action(
    id="knowledge.workbench.types_tab",
    label="Switch to Types tab",
    category="Knowledge",
    description="Activate the Types editing tab.",
    scope="knowledge",
)
SWITCH_TO_INSTANCES_TAB = Action(
    id="knowledge.workbench.instances_tab",
    label="Switch to Instances tab",
    category="Knowledge",
    description="Activate the Instances editing tab.",
    scope="knowledge",
)

# Link-type view control actions
LINKTYPE_TOGGLE_FILTER = Action(
    id="linktype.toggle_filter",
    label="Toggle link filter",
    category="Graph Controls",
    description="Toggle the filter flag for a specific link type.",
    scope="graph_view",
)
LINKTYPE_TOGGLE_VISIBILITY = Action(
    id="linktype.toggle_visibility",
    label="Toggle link visibility",
    category="Graph Controls",
    description="Toggle the visibility flag for a specific link type.",
    scope="graph_view",
)
LINKTYPE_TOGGLE_GHOST = Action(
    id="linktype.toggle_ghost",
    label="Toggle link ghost mode",
    category="Graph Controls",
    description="Toggle the ghost flag for a specific link type (visual-only).",
    scope="graph_view",
)
LINKTYPE_TOGGLE_SELECTABLE = Action(
    id="linktype.toggle_selectable",
    label="Toggle link selectability",
    category="Graph Controls",
    description="Toggle the selectable flag for a specific link type.",
    scope="graph_view",
)

# Graph frontier and view management actions
GRAPH_EXPAND_ALL = Action(
    id="graph.expand_all",
    label="Expand all (show frontier)",
    category="Graph Controls",
    description="Show all nodes reachable from the current selection.",
    scope="graph_view",
)
GRAPH_COLLAPSE_ALL = Action(
    id="graph.collapse_all",
    label="Collapse all (show selection)",
    category="Graph Controls",
    description="Hide all nodes except selected or root nodes.",
    scope="graph_view",
)
GRAPH_FRONTIER_TRAVERSE = Action(
    id="graph.frontier_traverse",
    label="Compute frontier",
    category="Graph Controls",
    description="Compute and display the frontier reachable from current selection.",
    scope="graph_view",
)

ACTIONS: list[Action] = [
    REPO_NEW,
    REPO_OPEN,
    REPO_SAVE_AS,
    PALETTE_SPAWN_SEARCH,
    FIELD_COLLAPSE_RECURSIVE,
    FIELD_PICK_REF,
    FIELD_CLEAR_REF,
    ADD_TYPE,
    ADD_INSTANCE,
    ADD_SLOT,
    SWITCH_TO_TYPES_TAB,
    SWITCH_TO_INSTANCES_TAB,
    LINKTYPE_TOGGLE_FILTER,
    LINKTYPE_TOGGLE_VISIBILITY,
    LINKTYPE_TOGGLE_GHOST,
    LINKTYPE_TOGGLE_SELECTABLE,
    GRAPH_EXPAND_ALL,
    GRAPH_COLLAPSE_ALL,
    GRAPH_FRONTIER_TRAVERSE,
]

DEFAULT_BINDINGS: list[tuple[Action, list[Binding]]] = [
    (REPO_NEW, [KeyBinding("Ctrl+N")]),
    (REPO_OPEN, [KeyBinding("Ctrl+O")]),
    (REPO_SAVE_AS, [KeyBinding("Ctrl+Shift+S")]),
    (PALETTE_SPAWN_SEARCH, [KeyBinding("Space")]),
    (
        FIELD_COLLAPSE_RECURSIVE,
        [
            MouseBinding(
                MouseButton.LEFT,
                frozenset({Modifier.ALT}),
                gesture=GestureKind.PRESS,
            )
        ],
    ),
    (FIELD_PICK_REF, [KeyBinding("Ctrl+L")]),
    (FIELD_CLEAR_REF, [KeyBinding("Delete")]),
    (ADD_TYPE, [KeyBinding("Ctrl+T")]),
    (ADD_INSTANCE, [KeyBinding("Ctrl+I")]),
    (ADD_SLOT, [KeyBinding("Ctrl+P")]),
    (SWITCH_TO_TYPES_TAB, [KeyBinding("Ctrl+1")]),
    (SWITCH_TO_INSTANCES_TAB, [KeyBinding("Ctrl+2")]),
    # Link-type controls — no default bindings, user-configurable via prefs editor
    (LINKTYPE_TOGGLE_FILTER, []),
    (LINKTYPE_TOGGLE_VISIBILITY, []),
    (LINKTYPE_TOGGLE_GHOST, []),
    (LINKTYPE_TOGGLE_SELECTABLE, []),
    # Graph controls — no default bindings, user-configurable via prefs editor
    (GRAPH_EXPAND_ALL, []),
    (GRAPH_COLLAPSE_ALL, []),
    (GRAPH_FRONTIER_TRAVERSE, []),
]


def register_defaults(bindings: InputBindings) -> None:
    """Register all default bindings for knowledge actions."""
    for action, binding_list in DEFAULT_BINDINGS:
        bindings.register(action, binding_list)


register_defaults(get_default_bindings())


__all__ = [
    "ACTIONS",
    "ADD_INSTANCE",
    "ADD_SLOT",
    "ADD_TYPE",
    "DEFAULT_BINDINGS",
    "FIELD_CLEAR_REF",
    "FIELD_COLLAPSE_RECURSIVE",
    "FIELD_PICK_REF",
    "GRAPH_COLLAPSE_ALL",
    "GRAPH_EXPAND_ALL",
    "GRAPH_FRONTIER_TRAVERSE",
    "LINKTYPE_TOGGLE_FILTER",
    "LINKTYPE_TOGGLE_GHOST",
    "LINKTYPE_TOGGLE_SELECTABLE",
    "LINKTYPE_TOGGLE_VISIBILITY",
    "PALETTE_SPAWN_SEARCH",
    "REPO_NEW",
    "REPO_OPEN",
    "REPO_SAVE_AS",
    "SWITCH_TO_INSTANCES_TAB",
    "SWITCH_TO_TYPES_TAB",
    "register_defaults",
]
