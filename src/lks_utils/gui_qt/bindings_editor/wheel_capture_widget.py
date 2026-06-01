"""QWheelCaptureWidget — wheel direction + modifier selector."""
from __future__ import annotations

from lks_utils.input.binding import WheelBinding, Modifier

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QComboBox,
    QCheckBox,
)
from PySide6.QtCore import Signal

_DIRECTIONS = [("Any", "any"), ("Up", "up"), ("Down", "down")]

_MODIFIERS = [
    ("Ctrl", Modifier.CTRL),
    ("Shift", Modifier.SHIFT),
    ("Alt", Modifier.ALT),
    ("Meta", Modifier.META),
]


class QWheelCaptureWidget(QWidget):
    """Combo box for scroll direction + modifier checkboxes."""

    binding_changed = Signal(object)  # WheelBinding

    def __init__(
        self,
        binding: WheelBinding | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._dir_combo = QComboBox()
        for label, _ in _DIRECTIONS:
            self._dir_combo.addItem(label)
        layout.addWidget(self._dir_combo)

        self._mod_checks: dict[Modifier, QCheckBox] = {}
        for label, mod in _MODIFIERS:
            cb = QCheckBox(label)
            self._mod_checks[mod] = cb
            layout.addWidget(cb)

        layout.addStretch()

        self._dir_combo.currentIndexChanged.connect(self._emit)
        for cb in self._mod_checks.values():
            cb.toggled.connect(self._emit)

        if binding is not None:
            self.set_binding(binding)

    # ------------------------------------------------------------------

    def binding(self) -> WheelBinding:
        direction = _DIRECTIONS[self._dir_combo.currentIndex()][1]
        mods = frozenset(
            m for m, cb in self._mod_checks.items() if cb.isChecked())
        return WheelBinding(modifiers=mods, direction=direction)

    def set_binding(self, b: WheelBinding) -> None:
        self._updating = True
        for i, (_, d) in enumerate(_DIRECTIONS):
            if d == b.direction:
                self._dir_combo.setCurrentIndex(i)
                break
        for mod, cb in self._mod_checks.items():
            cb.setChecked(mod in b.modifiers)
        self._updating = False

    # ------------------------------------------------------------------

    def _emit(self, *_) -> None:
        if not self._updating:
            self.binding_changed.emit(self.binding())


__all__ = ["QWheelCaptureWidget"]
