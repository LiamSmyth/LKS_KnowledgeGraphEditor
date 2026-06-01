"""`Canvas2D` actions and default bindings.

Importing this module registers the canvas's default bindings against
``lks_utils.input.get_default_bindings()``. Consumers can override
bindings post-hoc through the registry.
"""
from __future__ import annotations

from lks_utils.input import (
    Action,
    GestureKind,
    KeyBinding,
    Modifier,
    MouseBinding,
    MouseButton,
    WheelBinding,
    get_default_bindings,
)


CANVAS_PAN = Action(
    id="canvas2d.view.pan",
    label="Pan canvas",
    category="Canvas",
    description="Pan the viewport by dragging.",
    scope="canvas2d",
)

CANVAS_ZOOM_IN = Action(
    id="canvas2d.view.zoom_in",
    label="Zoom in",
    category="Canvas",
    scope="canvas2d",
)

CANVAS_ZOOM_OUT = Action(
    id="canvas2d.view.zoom_out",
    label="Zoom out",
    category="Canvas",
    scope="canvas2d",
)

CANVAS_ROTATE = Action(
    id="canvas2d.view.rotate",
    label="Rotate canvas",
    category="Canvas",
    description="Rotate the viewport. Snaps to nearest 90° on release.",
    scope="canvas2d",
)

CANVAS_RESET_VIEW = Action(
    id="canvas2d.view.reset",
    label="Reset view",
    category="Canvas",
    scope="canvas2d",
)

CANVAS_FIT_CONTENT = Action(
    id="canvas2d.view.fit_content",
    label="Fit content",
    category="Canvas",
    scope="canvas2d",
)

CANVAS_RESET_ZOOM = Action(
    id="canvas2d.view.reset_zoom",
    label="Zoom to 1:1",
    category="Canvas",
    scope="canvas2d",
)

CANVAS_PRIMARY = Action(
    id="canvas2d.input.primary",
    label="Primary action",
    category="Canvas",
    description="Routed to the topmost item under the cursor.",
    scope="canvas2d",
)

CANVAS_SECONDARY = Action(
    id="canvas2d.input.secondary",
    label="Secondary action",
    category="Canvas",
    description="Routed to the topmost item under the cursor (context menu).",
    scope="canvas2d",
)

CANVAS_ITEM_DRAG = Action(
    id="canvas2d.item.drag",
    label="Drag item",
    category="Canvas/Items",
    scope="canvas2d",
)

CANVAS_DESELECT_ALL = Action(
    id="canvas2d.selection.clear",
    label="Clear selection",
    category="Canvas/Selection",
    scope="canvas2d",
)

CANVAS_SELECT_ALL = Action(
    id="canvas2d.selection.select_all",
    label="Select all",
    category="Canvas/Selection",
    scope="canvas2d",
)

CANVAS_DELETE_SELECTED = Action(
    id="canvas2d.selection.delete_selected",
    label="Delete selected",
    category="Canvas/Selection",
    scope="canvas2d",
)

CANVAS_UNDO = Action(
    id="canvas2d.edit.undo",
    label="Undo",
    category="Canvas/Edit",
    scope="canvas2d",
)

CANVAS_REDO = Action(
    id="canvas2d.edit.redo",
    label="Redo",
    category="Canvas/Edit",
    scope="canvas2d",
)

CANVAS_COPY = Action(
    id="canvas2d.clipboard.copy",
    label="Copy",
    category="Canvas/Clipboard",
    scope="canvas2d",
)

CANVAS_CUT = Action(
    id="canvas2d.clipboard.cut",
    label="Cut",
    category="Canvas/Clipboard",
    scope="canvas2d",
)

CANVAS_PASTE = Action(
    id="canvas2d.clipboard.paste",
    label="Paste",
    category="Canvas/Clipboard",
    scope="canvas2d",
)

# Bookmark actions: one save + one restore per slot 1-9.
# Default key bindings are intentionally NOT registered here; subclasses
# or applications opt in to bind these (e.g. Ctrl+Shift+1 to save slot 1,
# Ctrl+1 to restore slot 1).
BOOKMARK_SAVE_1 = Action(id="canvas2d.bookmark.save.1",
                         label="Save View 1", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_2 = Action(id="canvas2d.bookmark.save.2",
                         label="Save View 2", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_3 = Action(id="canvas2d.bookmark.save.3",
                         label="Save View 3", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_4 = Action(id="canvas2d.bookmark.save.4",
                         label="Save View 4", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_5 = Action(id="canvas2d.bookmark.save.5",
                         label="Save View 5", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_6 = Action(id="canvas2d.bookmark.save.6",
                         label="Save View 6", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_7 = Action(id="canvas2d.bookmark.save.7",
                         label="Save View 7", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_8 = Action(id="canvas2d.bookmark.save.8",
                         label="Save View 8", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_SAVE_9 = Action(id="canvas2d.bookmark.save.9",
                         label="Save View 9", category="Canvas/Bookmarks", scope="canvas2d")

BOOKMARK_RESTORE_1 = Action(id="canvas2d.bookmark.restore.1",
                            label="Restore View 1", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_2 = Action(id="canvas2d.bookmark.restore.2",
                            label="Restore View 2", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_3 = Action(id="canvas2d.bookmark.restore.3",
                            label="Restore View 3", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_4 = Action(id="canvas2d.bookmark.restore.4",
                            label="Restore View 4", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_5 = Action(id="canvas2d.bookmark.restore.5",
                            label="Restore View 5", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_6 = Action(id="canvas2d.bookmark.restore.6",
                            label="Restore View 6", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_7 = Action(id="canvas2d.bookmark.restore.7",
                            label="Restore View 7", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_8 = Action(id="canvas2d.bookmark.restore.8",
                            label="Restore View 8", category="Canvas/Bookmarks", scope="canvas2d")
BOOKMARK_RESTORE_9 = Action(id="canvas2d.bookmark.restore.9",
                            label="Restore View 9", category="Canvas/Bookmarks", scope="canvas2d")


def register_canvas2d_defaults() -> None:
    """Register default bindings against the process registry.

    Idempotent: safe to call multiple times.
    """
    bindings = get_default_bindings()
    bindings.register(
        CANVAS_PAN,
        [
            MouseBinding(MouseButton.MIDDLE, gesture=GestureKind.DRAG),
            MouseBinding(MouseButton.LEFT, frozenset({Modifier.ALT}),
                         gesture=GestureKind.DRAG),
        ],
    )
    bindings.register(
        CANVAS_ZOOM_IN,
        [WheelBinding(direction="up")],
    )
    bindings.register(
        CANVAS_ZOOM_OUT,
        [WheelBinding(direction="down")],
    )
    bindings.register(
        CANVAS_ROTATE,
        [MouseBinding(
            MouseButton.LEFT,
            frozenset({Modifier.ALT, Modifier.SHIFT}),
            gesture=GestureKind.DRAG,
        )],
    )
    bindings.register(
        CANVAS_RESET_VIEW,
        [KeyBinding("Home")],
    )
    bindings.register(
        CANVAS_FIT_CONTENT,
        [KeyBinding("Ctrl+0")],
    )
    bindings.register(
        CANVAS_RESET_ZOOM,
        [KeyBinding("Ctrl+1")],
    )
    bindings.register(
        CANVAS_PRIMARY,
        [
            MouseBinding(MouseButton.LEFT, gesture=GestureKind.PRESS),
            MouseBinding(MouseButton.LEFT, gesture=GestureKind.DRAG),
            MouseBinding(MouseButton.LEFT, gesture=GestureKind.RELEASE),
            MouseBinding(
                MouseButton.LEFT,
                modifiers=frozenset({Modifier.SHIFT}),
                gesture=GestureKind.PRESS,
            ),
        ],
    )
    bindings.register(
        CANVAS_SECONDARY,
        [MouseBinding(MouseButton.RIGHT, gesture=GestureKind.PRESS)],
    )
    bindings.register(
        CANVAS_ITEM_DRAG,
        [MouseBinding(MouseButton.LEFT, gesture=GestureKind.DRAG)],
    )
    bindings.register(
        CANVAS_DESELECT_ALL,
        [KeyBinding("Escape")],
    )
    bindings.register(
        CANVAS_SELECT_ALL,
        [KeyBinding("Ctrl+A")],
    )
    bindings.register(
        CANVAS_DELETE_SELECTED,
        [KeyBinding("Delete"), KeyBinding("Del")],
    )
    bindings.register(
        CANVAS_UNDO,
        [KeyBinding("Ctrl+Z")],
    )
    bindings.register(
        CANVAS_REDO,
        [KeyBinding("Ctrl+Y"), KeyBinding("Ctrl+Shift+Z")],
    )
    bindings.register(
        CANVAS_COPY,
        [KeyBinding("Ctrl+C")],
    )
    bindings.register(
        CANVAS_CUT,
        [KeyBinding("Ctrl+X")],
    )
    bindings.register(
        CANVAS_PASTE,
        [KeyBinding("Ctrl+V")],
    )


# Register on import so widgets can rely on defaults being present.
register_canvas2d_defaults()


__all__ = [
    "CANVAS_PAN",
    "CANVAS_ZOOM_IN",
    "CANVAS_ZOOM_OUT",
    "CANVAS_ROTATE",
    "CANVAS_RESET_VIEW",
    "CANVAS_FIT_CONTENT",
    "CANVAS_RESET_ZOOM",
    "CANVAS_PRIMARY",
    "CANVAS_SECONDARY",
    "CANVAS_ITEM_DRAG",
    "CANVAS_DESELECT_ALL",
    "CANVAS_SELECT_ALL",
    "CANVAS_DELETE_SELECTED",
    "CANVAS_UNDO",
    "CANVAS_REDO",
    "BOOKMARK_SAVE_1",
    "BOOKMARK_SAVE_2",
    "BOOKMARK_SAVE_3",
    "BOOKMARK_SAVE_4",
    "BOOKMARK_SAVE_5",
    "BOOKMARK_SAVE_6",
    "BOOKMARK_SAVE_7",
    "BOOKMARK_SAVE_8",
    "BOOKMARK_SAVE_9",
    "BOOKMARK_RESTORE_1",
    "BOOKMARK_RESTORE_2",
    "BOOKMARK_RESTORE_3",
    "BOOKMARK_RESTORE_4",
    "BOOKMARK_RESTORE_5",
    "BOOKMARK_RESTORE_6",
    "BOOKMARK_RESTORE_7",
    "BOOKMARK_RESTORE_8",
    "BOOKMARK_RESTORE_9",
    "register_canvas2d_defaults",
]
