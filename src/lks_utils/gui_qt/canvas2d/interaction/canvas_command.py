"""Abstract undo/redo command for Canvas2D."""
from __future__ import annotations

from abc import ABC, abstractmethod


class CanvasCommand(ABC):
    """Abstract command with execute/undo methods."""

    description: str = ""

    @abstractmethod
    def execute(self) -> None:
        """Apply the command mutation."""

    @abstractmethod
    def undo(self) -> None:
        """Revert the command mutation."""


__all__ = ["CanvasCommand"]
