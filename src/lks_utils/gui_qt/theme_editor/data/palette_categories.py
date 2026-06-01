# Palette slot name prefix → display category name.
# Keys are matched as exact prefixes of Palette field names.
# Order determines display order in the editor.
PALETTE_CATEGORIES: dict[str, str] = {
    "canvas": "Canvas",
    "panel": "Panel",
    "text": "Text",
    "border": "Borders",
    "grid": "Grid",
    "handle": "Handles",
    "item": "Items",
    "selection": "Selection",
    "snap": "Snap & Drop",
    "drop": "Snap & Drop",
    "accent": "Accent",
    "success": "Status",
    "warning": "Status",
    "error": "Status",
    "info": "Status",
    "button": "Controls",
    "input": "Controls",
    "overlay": "Overlays",
}

OTHER_CATEGORY = "Other"

__all__ = ["PALETTE_CATEGORIES", "OTHER_CATEGORY"]
