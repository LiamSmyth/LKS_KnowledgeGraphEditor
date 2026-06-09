"""DragCapability — interactive drag with MoveObjectsCommand commit."""
from __future__ import annotations

from typing import TYPE_CHECKING

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability import CanvasObjectCapability
from lks_utils.gui_qt.canvas2d.interaction.actions import CANVAS_PRIMARY
from lks_utils.gui_qt.canvas2d.interaction.canvas_commands.command_move_objects import (
    MoveObjectsCommand,
)

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
        CapabilityHostObject,
    )
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent


class DragCapability(CanvasObjectCapability):
    """Drag the host in world space; commit returns :class:`MoveObjectsCommand`."""

    capability_id = "drag"
    schema_version = 1

    def __init__(self) -> None:
        super().__init__()
        self._active = False
        self._accumulated_delta: tuple[float, float] = (0.0, 0.0)
        self._last_world_pos: tuple[float, float] | None = None

    def apply_delta(
        self,
        host: CapabilityHostObject,
        world_delta: tuple[float, float],
    ) -> None:
        """Apply *world_delta* during drag; override for bespoke semantics."""
        dx, dy = world_delta
        host.on_drag((dx, dy))
        ax, ay = self._accumulated_delta
        self._accumulated_delta = (ax + dx, ay + dy)

    def handle_input(self, event: CanvasInputEvent) -> bool:
        if event.action.id != CANVAS_PRIMARY.id:
            return False
        host = self._host
        if host is None:
            return False

        if event.phase == "press":
            self.begin_preview()
            self._active = True
            self._last_world_pos = event.world_pos
            host.on_drag_begin(event.world_pos)
            return True

        if not self._active:
            return False

        if event.phase == "drag":
            if self._last_world_pos is not None:
                dx = event.world_pos[0] - self._last_world_pos[0]
                dy = event.world_pos[1] - self._last_world_pos[1]
                self.apply_delta(host, (dx, dy))
                host.request_repaint()
            self._last_world_pos = event.world_pos
            return True

        if event.phase == "release":
            self._active = False
            self._last_world_pos = None
            host.on_drag_end()
            cmd = self.commit()
            if cmd is not None:
                host.push_command(cmd, already_executed=True)
            return True

        return False

    def begin_preview(self) -> None:
        self._accumulated_delta = (0.0, 0.0)
        self._last_world_pos = None

    def cancel_preview(self) -> None:
        host = self._host
        if host is None:
            return
        dx, dy = self._accumulated_delta
        if abs(dx) > 1e-9 or abs(dy) > 1e-9:
            host.on_drag((-dx, -dy))
        self._accumulated_delta = (0.0, 0.0)
        self._active = False
        self._last_world_pos = None
        host.on_drag_end()

    def commit(self):
        host = self._host
        if host is None:
            return None
        dx, dy = self._accumulated_delta
        self._accumulated_delta = (0.0, 0.0)
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None
        return MoveObjectsCommand([(host, dx, dy)])


__all__ = ["DragCapability"]
