"""QTypographySection — reflective editor for a Typography dataclass."""
from __future__ import annotations

import dataclasses

from lks_utils.theme.typography import Typography

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QSpinBox,
    QFontComboBox,
    QGroupBox,
    QVBoxLayout,
    QScrollArea,
    QLabel,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Signal

_FAMILY_FIELDS = {"ui_family", "mono_family", "hud_family"}
_SIZE_RANGE = (6, 72)


class QTypographySection(QWidget):
    """Reflective editor for Typography family + size fields."""

    typography_changed = Signal(object)  # Typography

    def __init__(
        self,
        typography: Typography,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._typography = typography
        self._family_combos: dict[str, QFontComboBox] = {}
        self._size_spins: dict[str, QSpinBox] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(4, 4, 4, 4)
        inner_layout.setSpacing(8)

        # Group family + its associated sizes together
        groups = [
            ("UI Font", "ui_family", ["ui_size_pt"]),
            ("Monospace Font", "mono_family", ["mono_size_pt"]),
            ("HUD Font", "hud_family", ["hud_size_pt"]),
            ("Sizes", None, ["heading_size_pt", "small_size_pt"]),
        ]

        for group_label, family_field, size_fields in groups:
            box = QGroupBox(group_label)
            form = QFormLayout(box)
            form.setContentsMargins(4, 2, 4, 4)
            form.setSpacing(4)

            if family_field:
                combo = QFontComboBox()
                combo.setCurrentFont(QFont(getattr(typography, family_field)))
                combo.currentFontChanged.connect(
                    lambda f, fn=family_field: self._on_family_changed(
                        fn, f.family())
                )
                self._family_combos[family_field] = combo
                form.addRow("Family", combo)

            for sf in size_fields:
                spin = QSpinBox()
                spin.setRange(*_SIZE_RANGE)
                spin.setValue(getattr(typography, sf))
                spin.setSuffix(" pt")
                spin.valueChanged.connect(
                    lambda val, fn=sf: self._on_size_changed(fn, val)
                )
                self._size_spins[sf] = spin
                form.addRow(sf.replace("_", " "), spin)

            # Live preview label
            preview = QLabel("The quick brown fox jumps over the lazy dog.")
            preview.setWordWrap(True)
            preview.setObjectName(f"preview_{family_field or 'sizes'}")
            form.addRow("Preview", preview)
            box.setProperty("_preview_label", preview)

            inner_layout.addWidget(box)

        inner_layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------

    def typography(self) -> Typography:
        return self._typography

    def set_typography(self, typography: Typography) -> None:
        self._typography = typography
        for fn, combo in self._family_combos.items():
            combo.blockSignals(True)
            combo.setCurrentFont(QFont(getattr(typography, fn)))
            combo.blockSignals(False)
        for fn, spin in self._size_spins.items():
            spin.blockSignals(True)
            spin.setValue(getattr(typography, fn))
            spin.blockSignals(False)

    # ------------------------------------------------------------------

    def _on_family_changed(self, field_name: str, family: str) -> None:
        self._typography = dataclasses.replace(
            self._typography, **{field_name: family}
        )
        self.typography_changed.emit(self._typography)

    def _on_size_changed(self, field_name: str, value: int) -> None:
        self._typography = dataclasses.replace(
            self._typography, **{field_name: value}
        )
        self.typography_changed.emit(self._typography)


__all__ = ["QTypographySection"]
