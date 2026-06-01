"""Capability flags for optional Canvas2D interactions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Canvas2DCapabilities:
    """Enable or disable optional interaction features in Canvas2DWidget."""

    allow_selection: bool = True
    bring_selected_to_front: bool = True
    allow_multi_select: bool = False
    allow_range_select: bool = False
    allow_drag: bool = True
    allow_add_remove: bool = True
    allow_undo_redo: bool = True
    allow_clipboard: bool = True


__all__ = ["Canvas2DCapabilities"]
