"""Command to add a single `CanvasItem` to a `Scene2D`."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.command_history import CanvasCommand

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_item import CanvasItem
    from lks_utils.gui_qt.canvas2d.scene2d import Scene2D


class AddItemCommand(CanvasCommand):
    """Push this command to add *item* to *scene*; undo removes it."""

    description = "Add item"

    def __init__(self, scene: Scene2D, item: CanvasItem) -> None:
        self._scene = scene
        self._item = item

    def execute(self) -> None:
        self._scene.add_item(self._item)

    def undo(self) -> None:
        self._scene.remove_item(self._item)


__all__ = ["AddItemCommand"]
