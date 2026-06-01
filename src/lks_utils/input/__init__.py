"""Input bindings: remappable shortcuts and gestures.

Every keyboard shortcut, mouse gesture, wheel action, and tablet gesture in
the codebase MUST be declared as an `Action` and registered with an
`InputBindings` instance. Widgets resolve events through the registry
instead of hard-coding modifier or button checks.

This makes the entire input surface:

* discoverable (a single registry lists every action in the app);
* remappable (users can override defaults; persisted as JSON);
* documentable (each action has an id, label, and category);
* testable (unit tests can assert "this gesture triggers that action"
  without going through Qt event synthesis).

See ``copilot_input_bindings.instructions.md`` for the design rules.
"""
from __future__ import annotations

from lks_utils.input.action import Action
from lks_utils.input.binding import (
    Binding,
    KeyBinding,
    MouseBinding,
    MouseButton,
    Modifier,
    GestureKind,
    WheelBinding,
)
from lks_utils.input.bindings_registry import InputBindings, get_default_bindings
from lks_utils.input.per_app_override import (
    load_per_app_overrides,
    overrides_path,
    save_per_app_overrides,
)
from lks_utils.input.scope_protocol import HasInputScope
from lks_utils.input.scroll_physics import (
    MomentumDecay,
    VelocitySampler,
    WheelLerp,
)


__all__ = [
    "Action",
    "Binding",
    "KeyBinding",
    "MouseBinding",
    "MouseButton",
    "Modifier",
    "GestureKind",
    "WheelBinding",
    "InputBindings",
    "MomentumDecay",
    "VelocitySampler",
    "WheelLerp",
    "get_default_bindings",
    "HasInputScope",
    "load_per_app_overrides",
    "overrides_path",
    "save_per_app_overrides",
]
