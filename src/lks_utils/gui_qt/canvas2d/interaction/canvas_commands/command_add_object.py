"""Command to add a single `CanvasObject` to a `Scene2D`."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_object import CanvasObject
    from lks_utils.gui_qt.canvas2d.core.scene2d import Scene2D


class AddObjectCommand(CanvasCommand):
    """Push this command to add *obj* to *scene*; undo removes it."""

    description = "Add object"

    def __init__(self, scene: Scene2D, obj: CanvasObject) -> None:
        self._scene = scene
        self._object = obj

    def execute(self) -> None:
        self._scene.add_object(self._object)

    def undo(self) -> None:
        self._scene.remove_object(self._object)


__all__ = ["AddObjectCommand"]
