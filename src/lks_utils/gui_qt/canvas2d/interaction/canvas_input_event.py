"""`CanvasInputEvent`: a normalised input event delivered to canvas objects."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

from lks_utils.input import Action, Modifier


PhaseLiteral = Literal["press", "drag", "release", "wheel", "move"]


@dataclass(frozen=True, slots=True)
class CanvasInputEvent:
    """A canvas input event normalised by `Canvas2D`'s input dispatcher.

    Attributes:
        action: The bound `Action` that fired this event (e.g.
            ``CANVAS_PRIMARY``). For pure hover ``move`` events the
            action may be a sentinel ``Action`` named
            ``"canvas2d.input.move"``.
        phase: One of ``"press"``, ``"drag"``, ``"release"``,
            ``"wheel"``, ``"move"``.
        world_pos: Cursor position in world coordinates.
        screen_pos: Cursor position in screen pixels.
        pressure: 0..1, from tablet; 1.0 for mouse.
        tilt: ``(tilt_x, tilt_y)`` from tablet; ``(0, 0)`` for mouse.
        modifiers: Frozenset of held modifiers.
        delta: For ``wheel`` and ``drag`` phases — pixel delta since the
            previous event in the same gesture; ``None`` otherwise.
        key: Optional Qt key code for keyboard-originated events.
        text: Optional typed text payload for keyboard-originated events.
        is_tablet: True if this came from a `QTabletEvent`.
        timestamp_ns: Monotonic nanosecond timestamp.
    """

    action: Action
    phase: PhaseLiteral
    world_pos: tuple[float, float]
    screen_pos: tuple[float, float]
    pressure: float = 1.0
    tilt: tuple[float, float] = (0.0, 0.0)
    modifiers: frozenset[Modifier] = field(default_factory=frozenset)
    delta: tuple[float, float] | None = None
    key: int | None = None
    text: str = ""
    is_tablet: bool = False
    timestamp_ns: int = field(default_factory=lambda: time.monotonic_ns())


# Sentinel action for plain hover-move events not bound to anything.
CANVAS_MOVE = Action(
    id="canvas2d.input.move",
    label="Cursor move",
    category="Canvas",
    description="Internal: hover move; never bound by users.",
)

# Sentinel action for wheel events routed to items under the cursor.
# Items that return True from handle_input for this action consume the
# event before the canvas-level zoom gesture fires.  ``delta`` carries
# (angle_delta_x, angle_delta_y) in Qt angle units (1 notch ≈ 120).
CANVAS_OBJECT_WHEEL = Action(
    id="canvas2d.input.item_wheel",
    label="Item wheel",
    category="Canvas",
    description=(
        "Internal: wheel event offered to the canvas object under the cursor "
        "before the canvas handles zoom. Items return True to consume."
    ),
)

# Sentinel action for keyboard events routed to the canvas object under
# the cursor (or active capture object). Adapters can use ``key``/``text``
# to synthesize toolkit-specific key events.
CANVAS_OBJECT_KEY = Action(
    id="canvas2d.input.item_key",
    label="Item key",
    category="Canvas",
    description=(
        "Internal: key event offered to canvas objects for text-entry "
        "widgets rendered via adapters."
    ),
)


__all__ = [
    "CanvasInputEvent",
    "CANVAS_OBJECT_KEY",
    "CANVAS_OBJECT_WHEEL",
    "CANVAS_MOVE",
    "PhaseLiteral",
]
