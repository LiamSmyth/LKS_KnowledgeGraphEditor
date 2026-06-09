"""Stock :class:`CanvasObjectCapability` implementations."""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities.capability_drag import DragCapability
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities.capability_resize_rect import (
    ResizeRectCapability,
)
from lks_utils.gui_qt.canvas2d.canvas_objects.canvas_object_capabilities.capability_selectable import (
    SelectableCapability,
)

__all__ = ["DragCapability", "ResizeRectCapability", "SelectableCapability"]
