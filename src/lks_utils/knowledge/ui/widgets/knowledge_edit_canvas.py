"""Shared Canvas2D base for editable knowledge surfaces."""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.canvas2d_capabilities import Canvas2DCapabilities
from lks_utils.gui_qt.canvas2d import Canvas2DWidget
from lks_utils.gui_qt.canvas2d.overlays import DotGridOverlay


class QKnowledgeEditCanvasWidget(Canvas2DWidget):
    """Knowledge-specific edit canvas with standard dot-grid defaults."""

    def __init__(
        self,
        parent=None,
        *,
        capabilities: Canvas2DCapabilities | None = None,
        show_dot_grid: bool = True,
        dot_grid_scale: float = 84.0,
        dot_grid_subdivisions: int = 3,
    ) -> None:
        super().__init__(parent, capabilities=capabilities)
        if show_dot_grid:
            self.add_overlay(
                DotGridOverlay(
                    grid_scale=dot_grid_scale,
                    subdivisions=dot_grid_subdivisions,
                )
            )


__all__ = ["QKnowledgeEditCanvasWidget"]
