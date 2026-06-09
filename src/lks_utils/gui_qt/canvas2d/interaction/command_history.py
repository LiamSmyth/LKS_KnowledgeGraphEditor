"""Undo/redo command history for Canvas2D."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand


class CommandHistory(QObject):
    """Simple linear command history with undo/redo."""

    history_changed = Signal()
    can_undo_changed = Signal(bool)
    can_redo_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._done: list[CanvasCommand] = []
        self._undone: list[CanvasCommand] = []

    def push(self, cmd: CanvasCommand) -> None:
        cmd.execute()
        self._done.append(cmd)
        self._undone.clear()
        self._emit_state()

    def push_already_executed(self, cmd: CanvasCommand) -> None:
        """Record *cmd* in history without calling :meth:`execute` again.

        Use this when the command's side-effects were already applied live
        (e.g. during an interactive drag).  Undo/redo still work normally.
        """
        self._done.append(cmd)
        self._undone.clear()
        self._emit_state()

    def undo(self) -> None:
        if not self._done:
            return
        cmd = self._done.pop()
        cmd.undo()
        self._undone.append(cmd)
        self._emit_state()

    def redo(self) -> None:
        if not self._undone:
            return
        cmd = self._undone.pop()
        cmd.execute()
        self._done.append(cmd)
        self._emit_state()

    def clear(self) -> None:
        if not self._done and not self._undone:
            return
        self._done.clear()
        self._undone.clear()
        self._emit_state()

    def can_undo(self) -> bool:
        return bool(self._done)

    def can_redo(self) -> bool:
        return bool(self._undone)

    def _emit_state(self) -> None:
        self.history_changed.emit()
        self.can_undo_changed.emit(self.can_undo())
        self.can_redo_changed.emit(self.can_redo())


__all__ = ["CommandHistory"]
