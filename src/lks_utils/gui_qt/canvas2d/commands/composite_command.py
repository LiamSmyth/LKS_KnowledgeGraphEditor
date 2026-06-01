"""Composite command to group multiple CanvasCommand steps."""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.command_history import CanvasCommand


class CompositeCommand(CanvasCommand):
    """Execute and undo many commands as one history entry."""

    def __init__(
        self,
        commands: list[CanvasCommand],
        description: str = "Composite command",
    ) -> None:
        self._commands = list(commands)
        self.description = description

    def execute(self) -> None:
        for command in self._commands:
            command.execute()

    def undo(self) -> None:
        for command in reversed(self._commands):
            command.undo()


__all__ = ["CompositeCommand"]
