"""Built-in overlays for `Canvas2D`."""
from __future__ import annotations

from lks_utils.gui_qt.canvas2d.overlays.canvas_border_overlay import (
    CanvasBorderOverlay,
)
from lks_utils.gui_qt.canvas2d.overlays.color_backdrop import ColorBackdrop
from lks_utils.gui_qt.canvas2d.overlays.coord_hud_overlay import CoordHudOverlay
from lks_utils.gui_qt.canvas2d.overlays.checkerboard_overlay import (
    CheckerboardOverlay,
)
from lks_utils.gui_qt.canvas2d.overlays.axes_lines_overlay import (
    AxesLinesOverlay,
)
from lks_utils.gui_qt.canvas2d.overlays.dot_grid_overlay import (
    DotGridOverlay,
    DotGridOverlayTheme,
)
from lks_utils.gui_qt.canvas2d.overlays.home_grid_overlay import (
    HomeGridOverlay,
)
from lks_utils.gui_qt.canvas2d.overlays.texture_canvas_overlay import (
    TextureCanvasOverlay,
)
from lks_utils.gui_qt.canvas2d.overlays.world_grid_overlay import WorldGridOverlay

__all__ = ["DotGridOverlay", "DotGridOverlayTheme", "CanvasBorderOverlay",
           "CoordHudOverlay", "ColorBackdrop", "WorldGridOverlay",
           "CheckerboardOverlay", "TextureCanvasOverlay", "AxesLinesOverlay",
           "HomeGridOverlay"]
