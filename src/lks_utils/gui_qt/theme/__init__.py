"""Theme and styling for PySide6 GUIs.

The theme package is the single source of truth for colours, spacing,
typography, and motion timings (Phase 17h). All painter / canvas / GPU
widgets should consume constants from here rather than embed literal
``QColor(...)``, ``"#RRGGBB"``, pixel sizes, or millisecond durations.

Submodules:
    colors   — legacy ttkbootstrap-derived semantic colour dict (``COLORS``)
    palette  — painter / canvas semantic colour palette (``PALETTE``)
    spacing  — paddings, gaps, row heights, radii, icon sizes
    typography — font families, sizes, weights
    motion   — animation durations and momentum-decay time constants

Stage 2 (Qt adapter):
    color_adapter        — Color <-> QColor
    theme_provider       — QThemeProvider singleton
    theme_aware_mixin    — ThemeAwareMixin for QWidget subclasses
    qpalette_adapter     — qpalette_for_theme
    stylesheet_generator — theme_to_qss
    apply_theme          — apply_theme(app, theme=None)
    icon_recolor         — recolor_svg / recolor_svg_to_palette
"""

from __future__ import annotations
from lks_utils.gui_qt.theme import motion, palette, spacing, typography
from lks_utils.gui_qt.theme.colors import COLORS
from lks_utils.gui_qt.theme.dark_theme import DARK_QSS, apply_dark_theme
from lks_utils.gui_qt.theme.palette import PALETTE

# Stage 2 exports
from lks_utils.gui_qt.theme.color_adapter import to_qcolor, from_qcolor
from lks_utils.gui_qt.theme.theme_provider import QThemeProvider
from lks_utils.gui_qt.theme.theme_aware_mixin import ThemeAwareMixin
from lks_utils.gui_qt.theme.qpalette_adapter import qpalette_for_theme
from lks_utils.gui_qt.theme.stylesheet_generator import theme_to_qss
from lks_utils.gui_qt.theme.apply_theme import apply_theme
from lks_utils.gui_qt.theme.icon_recolor import recolor_svg, recolor_svg_to_palette

__all__ = [
    # Legacy
    "COLORS",
    "DARK_QSS",
    "PALETTE",
    "apply_dark_theme",
    "motion",
    "palette",
    "spacing",
    "typography",
    # Stage 2
    "QThemeProvider",
    "ThemeAwareMixin",
    "apply_theme",
    "from_qcolor",
    "qpalette_for_theme",
    "recolor_svg",
    "recolor_svg_to_palette",
    "theme_to_qss",
    "to_qcolor",
]
