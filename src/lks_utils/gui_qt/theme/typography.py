"""Typography constants for PySide6 GUIs.

Named font sizes / weights. Phase 17h. Stylesheet authors should
consume ``SIZE_*`` and ``FONT_FAMILY_*`` rather than bare ``px`` /
``pt`` / family strings.
"""
from __future__ import annotations


# Font families (system-default fallbacks).
FONT_FAMILY_UI: str = "Segoe UI, system-ui, sans-serif"
FONT_FAMILY_MONO: str = "Cascadia Code, Consolas, Menlo, monospace"

# Font sizes in pixels.
SIZE_XS: int = 10
SIZE_SM: int = 11
SIZE_MD: int = 13
SIZE_LG: int = 15
SIZE_XL: int = 18
SIZE_XXL: int = 22

# Weights (Qt-friendly numeric weights).
WEIGHT_NORMAL: int = 400
WEIGHT_MEDIUM: int = 500
WEIGHT_BOLD: int = 600


__all__ = [
    "FONT_FAMILY_UI", "FONT_FAMILY_MONO",
    "SIZE_XS", "SIZE_SM", "SIZE_MD", "SIZE_LG", "SIZE_XL", "SIZE_XXL",
    "WEIGHT_NORMAL", "WEIGHT_MEDIUM", "WEIGHT_BOLD",
]
