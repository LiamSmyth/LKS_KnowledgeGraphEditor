"""QPaletteSection — reflective editor for a Palette dataclass."""
from __future__ import annotations

import dataclasses

from lks_utils.theme.palette import Palette
from lks_utils.theme.color import Color
from lks_utils.gui_qt.theme_editor.color_swatch_widget import QColorSwatchWidget
from lks_utils.gui_qt.theme_editor.data.palette_categories import (
    PALETTE_CATEGORIES,
    OTHER_CATEGORY,
)

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QScrollArea,
    QSizePolicy,
)
from PySide6.QtCore import Signal


def _category_for(field_name: str) -> str:
    """Return the display category for a Palette field by name prefix."""
    for prefix, category in PALETTE_CATEGORIES.items():
        if field_name.startswith(prefix):
            return category
    return OTHER_CATEGORY


class QPaletteSection(QWidget):
    """Reflective editor for all 32 Palette colour slots.

    Emits ``palette_changed`` whenever any swatch is edited.
    """

    palette_changed = Signal(object)  # Palette

    def __init__(
        self,
        palette: Palette,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._palette = palette
        self._swatches: dict[str, QColorSwatchWidget] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(4)

        # Build category → list[field] map preserving insertion order
        categories: dict[str, list[dataclasses.Field]] = {}
        for field in dataclasses.fields(palette):
            if not isinstance(getattr(palette, field.name), Color):
                continue
            cat = _category_for(field.name)
            categories.setdefault(cat, []).append(field)

        for cat_name, fields in categories.items():
            group = QGroupBox(cat_name)
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(4, 2, 4, 4)
            group_layout.setSpacing(1)
            for field in fields:
                color_val: Color = getattr(palette, field.name)
                swatch = QColorSwatchWidget(field.name, color_val)
                swatch.color_changed.connect(
                    lambda c, fn=field.name: self._on_swatch_changed(fn, c)
                )
                self._swatches[field.name] = swatch
                group_layout.addWidget(swatch)
            inner_layout.addWidget(group)

        inner_layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------

    def palette(self) -> Palette:
        return self._palette

    def set_palette(self, palette: Palette) -> None:
        self._palette = palette
        for field_name, swatch in self._swatches.items():
            swatch.set_color(getattr(palette, field_name))

    # ------------------------------------------------------------------

    def _on_swatch_changed(self, field_name: str, color: Color) -> None:
        self._palette = dataclasses.replace(
            self._palette, **{field_name: color})
        self.palette_changed.emit(self._palette)


__all__ = ["QPaletteSection"]
