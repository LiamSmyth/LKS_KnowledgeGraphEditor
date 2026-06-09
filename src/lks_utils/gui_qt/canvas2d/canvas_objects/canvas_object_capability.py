"""Abstract base for attachable per-object canvas behaviors."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capability_host import (
        CapabilityHostObject,
    )
    from lks_utils.gui_qt.canvas2d.core.view_transform import ViewTransform
    from lks_utils.gui_qt.canvas2d.interaction.canvas_command import CanvasCommand
    from lks_utils.gui_qt.canvas2d.interaction.canvas_input_event import CanvasInputEvent
    from lks_utils.gui_qt.canvas2d.render.canvas_paint_context import CanvasPaintContext


class CanvasObjectCapability(ABC):
    """Optional behavior unit composed onto a :class:`CapabilityHostObject`."""

    capability_id: str
    schema_version: int = 1

    def __init__(self) -> None:
        self._host: CapabilityHostObject | None = None
        self._synthesized: bool = False

    @property
    def host(self) -> CapabilityHostObject | None:
        return self._host

    @property
    def is_synthesized(self) -> bool:
        """True when auto-created from legacy ``selectable`` / ``draggable`` flags."""
        return self._synthesized

    def bind(self, host: CapabilityHostObject) -> None:
        """Attach this capability to *host*."""
        self._host = host
        self._on_bind()

    def unbind(self) -> None:
        """Detach from the current host."""
        self._on_unbind()
        self._host = None

    def _on_bind(self) -> None:
        return None

    def _on_unbind(self) -> None:
        return None

    def handle_input(self, event: CanvasInputEvent) -> bool:
        """Return ``True`` when the event is consumed."""
        return False

    def hit_test_chrome(
        self,
        world_pos: tuple[float, float],
        *,
        zoom: float,
    ) -> bool:
        """Return ``True`` when *world_pos* hits chrome outside the host body."""
        return False

    def cursor_at(
        self,
        world_pos: tuple[float, float],
        *,
        zoom: float,
        screen_pos: tuple[float, float] | None = None,
        view: "ViewTransform | None" = None,
        viewport_size_px: tuple[float, float] | None = None,
    ) -> Qt.CursorShape | None:
        """Return a cursor shape when hovering capability chrome, else ``None``."""
        del world_pos, zoom, screen_pos, view, viewport_size_px
        return None

    def paint_chrome(self, ctx: CanvasPaintContext) -> None:
        """Draw capability-owned decoration above host content."""
        return None

    def serialize_state(self) -> dict:
        """Return capability-local state for persistence."""
        return {}

    def load_state(self, payload: dict) -> None:
        """Restore capability-local state from *payload*."""
        return None

    def begin_preview(self) -> None:
        """Start an interactive preview session."""
        return None

    def cancel_preview(self) -> None:
        """Abort preview and restore pre-preview state."""
        return None

    def commit(self) -> CanvasCommand | None:
        """Finalize preview and return a command for :class:`CommandHistory`."""
        return None


__all__ = ["CanvasObjectCapability"]
