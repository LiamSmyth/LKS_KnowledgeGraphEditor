"""Command to record a move of one or more `CanvasObject`s."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject


class MoveObjectsCommand(CanvasCommand):
    """Record the world-space delta for a completed drag move.

    ``pre_positions`` and ``post_positions`` are dicts mapping each object
    to its world origin *before* and *after* the move.  The command itself
    does NOT perform the initial move — that happens live during the drag.
    Calling :meth:`undo` calls ``on_drag_begin`` / ``on_drag`` / ``on_drag_end``
    in reverse to restore objects to their previous positions.

    Args:
        object_deltas: Sequence of ``(obj, dx, dy)`` tuples describing the
            total delta applied during the drag.  Redo re-applies the same
            delta; undo negates it.
    """

    description = "Move objects"

    def __init__(
        self,
        object_deltas: list[tuple[CanvasObject, float, float]],
    ) -> None:
        self._objects_deltas = list(object_deltas)

    def execute(self) -> None:
        for obj, dx, dy in self._objects_deltas:
            obj.on_drag_begin((0.0, 0.0))
            obj.on_drag((dx, dy))
            obj.on_drag_end()

    def undo(self) -> None:
        for obj, dx, dy in self._objects_deltas:
            obj.on_drag_begin((0.0, 0.0))
            obj.on_drag((-dx, -dy))
            obj.on_drag_end()


__all__ = ["MoveObjectsCommand"]
