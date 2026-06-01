"""QThemePreviewWidget — mini chrome preview reflecting a Theme."""
from __future__ import annotations

import dataclasses

from lks_utils.theme.theme import Theme
from lks_utils.gui_qt.theme.stylesheet_generator import theme_to_qss

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QGroupBox,
    QSlider,
    QCheckBox,
    QTabWidget,
    QLabel,
    QSizePolicy,
    QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QFont


class _PaletteSwatchPanel(QWidget):
    """64×64 grid of key palette colour blocks."""

    _SLOTS = [
        "canvas_bg",
        "panel_bg",
        "selection",
        "accent",
        "warning",
        "error",
        "item_outline",
        "text_primary",
    ]

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self.setFixedSize(144, 32)
        self._theme = theme

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        p = QPainter(self)
        w = self.width() // len(self._SLOTS)
        h = self.height()
        for i, slot in enumerate(self._SLOTS):
            color = getattr(self._theme.palette, slot)
            from lks_utils.gui_qt.theme.color_adapter import to_qcolor
            p.fillRect(i * w, 0, w, h, to_qcolor(color))
        p.end()


class QThemePreviewWidget(QWidget):
    """Small widget showing representative Qt chrome elements.

    Call :meth:`set_theme` to update the preview to any theme without
    affecting the rest of the application.
    """

    def __init__(
        self,
        theme: Theme,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._theme = theme
        self._build_ui()
        self._apply_theme(theme)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # ---- Controls row ----
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self._btn = QPushButton("Button")
        self._le = QLineEdit()
        self._le.setPlaceholderText("Input…")
        self._spin = QSpinBox()
        self._spin.setRange(0, 100)
        self._combo = QComboBox()
        self._combo.addItems(["Option A", "Option B"])
        self._check = QCheckBox("Check")
        for w in (self._btn, self._le, self._spin, self._combo, self._check):
            controls.addWidget(w)
        root.addLayout(controls)

        # ---- Slider row ----
        slider_row = QHBoxLayout()
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setValue(40)
        slider_row.addWidget(self._slider)
        root.addLayout(slider_row)

        # ---- GroupBox with swatches ----
        group = QGroupBox("Palette Swatches")
        g_layout = QHBoxLayout(group)
        self._swatches = _PaletteSwatchPanel(self._theme)
        self._typo_label = QLabel(
            "The quick brown fox jumps over the lazy dog.")
        self._typo_label.setWordWrap(True)
        g_layout.addWidget(self._swatches)
        g_layout.addWidget(self._typo_label)
        root.addWidget(group)

    def set_theme(self, theme: Theme) -> None:
        """Apply *theme* to this preview widget (does not touch the app)."""
        self._theme = theme
        self._apply_theme(theme)

    def _apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet(theme_to_qss(theme))
        self._swatches.set_theme(theme)
        t = theme.typography
        font = QFont(t.ui_family, t.ui_size_pt)
        self._typo_label.setFont(font)


__all__ = ["QThemePreviewWidget"]
