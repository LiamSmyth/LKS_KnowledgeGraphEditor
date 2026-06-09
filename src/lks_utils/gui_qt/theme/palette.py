"""Semantic colour palette for the painter and other GPU/canvas widgets.

Adds Phase 17h painter-specific semantic colours on top of the
ttkbootstrap-derived ``COLORS`` dict. Stylesheets and direct
``QColor(...)`` callsites in painter UI should resolve through
``PALETTE[...]``.

The palette intentionally covers names like ``canvas_bg``, ``dot_grid``,
``layer_row_hover``, ``selection_marquee`` — semantic, not literal —
so swapping themes later is one file.
"""
from __future__ import annotations


# Hex strings (so they can be used in QSS without conversion).
PALETTE: dict[str, str] = {
    # Canvas / viewport.
    "canvas_bg": "#1a1a1a",          # outside the document rect (dark)
    "canvas_fg_default": "#000000",  # default brush ink
    "dot_grid": "#2c2c2c",           # off-canvas dot-matrix dots
    "dot_grid_strong": "#404040",    # stronger dots every Nth
    "canvas_border": "#888888",      # 1px AA outline around document
    "canvas_drop_shadow": "#00000080",
    "tiling_central_tint": "#ffffff00",   # transparent — leave central tile alone
    "tiling_outer_tint": "#00000060",     # darken outer rings 38%

    # Layer panel.
    "layer_row_bg": "#262626",
    "layer_row_bg_alt": "#2a2a2a",
    "layer_row_hover": "#333333",
    "layer_row_active": "#3d5a87",
    "layer_thumb_border": "#1a1a1a",

    # Selection / marching ants.
    "selection_marquee": "#ffffff",
    "selection_marquee_alt": "#000000",

    # Minimap / pinned locations / overlays.
    "minimap_bg": "#181818c0",
    "minimap_viewport_outline": "#ffe066",
    "minimap_painted_outline": "#888888",
    "pin_marker": "#ffe066",

    # Region tool (Phase 18k).
    "export_region_outline": "#42a5f5",
    "export_region_outline_active": "#ffe066",
    "export_region_label_bg": "#000000a0",

    # Canvas2D demo / sample objects (used by the canvas2d demo widget
    # and the sample CanvasObject implementations). Kept here so the
    # canvas2d/ tree stays palette-clean per Phase F of the
    # 2026-04-29 canvas2d foundation checklist.
    "canvas2d_object_outline": "#222222",         # default object border
    "canvas2d_object_outline_minimap": "#111111",  # darker pen for minimap
    "canvas2d_text_label": "#000000",           # in-object label text
    "canvas2d_grid_minor": "#3a3a3a",           # GridLabelCanvasObject grid
    "canvas2d_grid_axis_x": "#ff2d2d",          # X axis (red)
    "canvas2d_grid_axis_y": "#66aa66",          # Y axis (green-ish)
    "canvas2d_hud_text": "#dddddd",             # CoordHudOverlay text
    "canvas2d_debug_bounds_stroke": "#ff0000",  # CanvasBoundsOverlay pen
    "canvas2d_debug_bounds_label": "#ff4444",   # CanvasBoundsOverlay label text
    "canvas2d_demo_backdrop": "#ff1a1a2e",      # ColorBackdrop demo default
    "canvas2d_node_header_bg": "#2a2a2a",
    "canvas2d_node_header_title": "#e8e8e8",
    "canvas2d_node_stroke": "#555555",
    "canvas2d_node_fill": "#1e1e1e",
    "canvas2d_node_header_subtitle": "#9ab0d0",
    "canvas2d_demo_node_header_bg": "#2a3344",
    "canvas2d_demo_node_header_title": "#e8eef8",
    "canvas2d_demo_node_fill": "#1a2030",
}


_LEGACY_PALETTE_ALIASES: dict[str, str] = {
    "canvas2d_item_outline": "canvas2d_object_outline",
    "canvas2d_item_outline_minimap": "canvas2d_object_outline_minimap",
}


def get(name: str) -> str:
    """Return the palette colour by name, raising a clear error if missing."""
    canonical = _LEGACY_PALETTE_ALIASES.get(name, name)
    if canonical not in PALETTE:
        raise KeyError(
            f"PALETTE has no colour {name!r}. "
            f"Add it to lks_utils/gui_qt/theme/palette.py."
        )
    return PALETTE[canonical]


__all__ = ["PALETTE", "get"]
