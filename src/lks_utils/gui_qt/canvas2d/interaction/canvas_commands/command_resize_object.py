"""Command to record a host-rect resize."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF

from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
        CapabilityHostObject,
    )


class ResizeObjectCommand(CanvasCommand):
    """Record a completed resize of a :class:`CapabilityHostObject`."""

    description = "Resize object"

    def __init__(
        self,
        host: CapabilityHostObject,
        old_rect: QRectF,
        new_rect: QRectF,
    ) -> None:
        self._host = host
        self._old_rect = QRectF(old_rect)
        self._new_rect = QRectF(new_rect)

    def execute(self) -> None:
        self._host.set_host_rect(self._new_rect)

    def undo(self) -> None:
        self._host.set_host_rect(self._old_rect)


__all__ = ["ResizeObjectCommand"]
