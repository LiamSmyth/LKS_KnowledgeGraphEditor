"""Command to record a move of one or more `CanvasItem`s."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.command_history import CanvasCommand

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem


class MoveItemsCommand(CanvasCommand):
    """Record the world-space delta for a completed drag move.

    ``pre_positions`` and ``post_positions`` are dicts mapping each item
    to its world origin *before* and *after* the move.  The command itself
    does NOT perform the initial move — that happens live during the drag.
    Calling :meth:`undo` calls ``on_drag_begin`` / ``on_drag`` / ``on_drag_end``
    in reverse to restore items to their previous positions.

    Args:
        items_deltas: Sequence of ``(item, dx, dy)`` tuples describing the
            total delta applied during the drag.  Redo re-applies the same
            delta; undo negates it.
    """

    description = "Move items"

    def __init__(
        self,
        items_deltas: list[tuple[CanvasItem, float, float]],
    ) -> None:
        self._items_deltas = list(items_deltas)

    def execute(self) -> None:
        for item, dx, dy in self._items_deltas:
            item.on_drag_begin((0.0, 0.0))
            item.on_drag((dx, dy))
            item.on_drag_end()

    def undo(self) -> None:
        for item, dx, dy in self._items_deltas:
            item.on_drag_begin((0.0, 0.0))
            item.on_drag((-dx, -dy))
            item.on_drag_end()


__all__ = ["MoveItemsCommand"]
