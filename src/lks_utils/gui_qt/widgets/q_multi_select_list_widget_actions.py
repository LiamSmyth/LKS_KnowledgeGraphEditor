"""Input actions for QMultiSelectListWidget."""
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

MULTI_SELECT_SINGLE = Action(
    id="gui_qt.multi_select.single",
    label="Select single item",
    category="GUI",
    description="Select one list item and clear previous selection.",
    scope="gui_qt.widgets",
)
MULTI_SELECT_TOGGLE = Action(
    id="gui_qt.multi_select.toggle",
    label="Toggle item selection",
    category="GUI",
    description="Ctrl+click to toggle one item in selection.",
    scope="gui_qt.widgets",
)
MULTI_SELECT_RANGE = Action(
    id="gui_qt.multi_select.range",
    label="Range select",
    category="GUI",
    description="Shift+click to select range from anchor to item.",
    scope="gui_qt.widgets",
)
MULTI_SELECT_ADD_RANGE = Action(
    id="gui_qt.multi_select.add_range",
    label="Add range to selection",
    category="GUI",
    description="Ctrl+Shift+click to add range from anchor.",
    scope="gui_qt.widgets",
)
MULTI_SELECT_SELECT_ALL = Action(
    id="gui_qt.multi_select.select_all",
    label="Select all items",
    category="GUI",
    description="Select all items in list.",
    scope="gui_qt.widgets",
)

DEFAULT_BINDINGS: list[tuple[Action, list[Binding]]] = [
    (
        MULTI_SELECT_SINGLE,
        [MouseBinding(MouseButton.LEFT, frozenset(),
                      gesture=GestureKind.PRESS)],
    ),
    (
        MULTI_SELECT_TOGGLE,
        [
            MouseBinding(
                MouseButton.LEFT,
                frozenset({Modifier.CTRL}),
                gesture=GestureKind.PRESS,
            )
        ],
    ),
    (
        MULTI_SELECT_RANGE,
        [
            MouseBinding(
                MouseButton.LEFT,
                frozenset({Modifier.SHIFT}),
                gesture=GestureKind.PRESS,
            )
        ],
    ),
    (
        MULTI_SELECT_ADD_RANGE,
        [
            MouseBinding(
                MouseButton.LEFT,
                frozenset({Modifier.CTRL, Modifier.SHIFT}),
                gesture=GestureKind.PRESS,
            )
        ],
    ),
    (MULTI_SELECT_SELECT_ALL, [KeyBinding("Ctrl+A")]),
]


def register_defaults(bindings: InputBindings) -> None:
    """Register default mouse and key bindings for multi-select list actions."""
    for action, binding_list in DEFAULT_BINDINGS:
        bindings.register(action, binding_list)


register_defaults(get_default_bindings())


__all__ = [
    "MULTI_SELECT_SINGLE",
    "MULTI_SELECT_TOGGLE",
    "MULTI_SELECT_RANGE",
    "MULTI_SELECT_ADD_RANGE",
    "MULTI_SELECT_SELECT_ALL",
    "DEFAULT_BINDINGS",
    "register_defaults",
]
