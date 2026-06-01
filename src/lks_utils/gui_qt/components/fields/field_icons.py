"""Icon helpers for field widgets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray
from PySide6.QtGui import QIcon
from PySide6.QtGui import QPixmap

from lks_utils.gui_qt.theme.icon_recolor import recolor_svg
from lks_utils.gui_qt.theme.palette import PALETTE


_ICON_CACHE: dict[str, QIcon] = {}


def _load_svg_icon(svg_name: str, *, stroke_color: str) -> QIcon:
    """Load an SVG icon and recolor stroke/fill for dark-theme visibility."""
    cached = _ICON_CACHE.get(svg_name)
    if cached is not None:
        return cached

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    svg_path = data_dir / svg_name
    svg_text = svg_path.read_text(encoding="utf-8")
    recolored = recolor_svg(svg_text, fill=stroke_color, stroke=stroke_color)

    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(recolored.encode("utf-8")), "SVG")
    icon = QIcon(pixmap)
    _ICON_CACHE[svg_name] = icon
    return icon


def get_field_revert_icon() -> QIcon:
    """Load the shared revert icon used by field widgets."""
    return _load_svg_icon("field_revert.svg", stroke_color=PALETTE["selection_marquee"])


def get_field_delete_icon() -> QIcon:
    """Load the shared delete icon used by cardinality row widgets."""
    return _load_svg_icon("field_delete.svg", stroke_color=PALETTE["selection_marquee"])


def get_field_grip_icon() -> QIcon:
    """Load the shared grip icon used by cardinality row widgets."""
    return _load_svg_icon("field_grip.svg", stroke_color=PALETTE["selection_marquee"])


def get_field_add_icon() -> QIcon:
    """Load the shared add icon used by cardinality list controls."""
    return _load_svg_icon("field_add.svg", stroke_color=PALETTE["selection_marquee"])
