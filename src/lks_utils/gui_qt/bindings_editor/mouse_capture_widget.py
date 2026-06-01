"""QMouseCaptureWidget — mouse button + modifier selector."""
from __future__ import annotations

from lks_utils.input.binding import MouseBinding, MouseButton, Modifier, GestureKind

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QComboBox,
    QCheckBox,
    QLabel,
)
from PySide6.QtCore import Signal

_BUTTONS = [
    ("Left", MouseButton.LEFT),
    ("Right", MouseButton.RIGHT),
    ("Middle", MouseButton.MIDDLE),
]

_GESTURES = [
    ("Click", GestureKind.CLICK),
    ("Press", GestureKind.PRESS),
    ("Release", GestureKind.RELEASE),
    ("Double-click", GestureKind.DOUBLE_CLICK),
    ("Drag", GestureKind.DRAG),
]

_MODIFIERS = [
    ("Ctrl", Modifier.CTRL),
    ("Shift", Modifier.SHIFT),
    ("Alt", Modifier.ALT),
    ("Meta", Modifier.META),
]


class QMouseCaptureWidget(QWidget):
    """Combo box (button) + combo box (gesture) + modifier checkboxes."""

    binding_changed = Signal(object)  # MouseBinding

    def __init__(
        self,
        binding: MouseBinding | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._btn_combo = QComboBox()
        for label, _ in _BUTTONS:
            self._btn_combo.addItem(label)
        layout.addWidget(self._btn_combo)

        self._gesture_combo = QComboBox()
        for label, _ in _GESTURES:
            self._gesture_combo.addItem(label)
        layout.addWidget(self._gesture_combo)

        self._mod_checks: dict[Modifier, QCheckBox] = {}
        for label, mod in _MODIFIERS:
            cb = QCheckBox(label)
            self._mod_checks[mod] = cb
            layout.addWidget(cb)

        layout.addStretch()

        self._btn_combo.currentIndexChanged.connect(self._emit)
        self._gesture_combo.currentIndexChanged.connect(self._emit)
        for cb in self._mod_checks.values():
            cb.toggled.connect(self._emit)

        if binding is not None:
            self.set_binding(binding)

    # ------------------------------------------------------------------

    def binding(self) -> MouseBinding:
        btn = _BUTTONS[self._btn_combo.currentIndex()][1]
        gesture = _GESTURES[self._gesture_combo.currentIndex()][1]
        mods = frozenset(
            m for m, cb in self._mod_checks.items() if cb.isChecked())
        return MouseBinding(button=btn, modifiers=mods, gesture=gesture)

    def set_binding(self, b: MouseBinding) -> None:
        self._updating = True
        for i, (_, btn) in enumerate(_BUTTONS):
            if btn == b.button:
                self._btn_combo.setCurrentIndex(i)
                break
        for i, (_, gesture) in enumerate(_GESTURES):
            if gesture == b.gesture:
                self._gesture_combo.setCurrentIndex(i)
                break
        for mod, cb in self._mod_checks.items():
            cb.setChecked(mod in b.modifiers)
        self._updating = False

    # ------------------------------------------------------------------

    def _emit(self, *_) -> None:
        if not self._updating:
            self.binding_changed.emit(self.binding())


__all__ = ["QMouseCaptureWidget"]
