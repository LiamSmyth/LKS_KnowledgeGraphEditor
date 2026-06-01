"""QKeyCaptureWidget — press-to-capture keyboard shortcut widget."""
from __future__ import annotations

from lks_utils.input.binding import KeyBinding

from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeySequence, QKeyEvent


_PLACEHOLDER = "— Click to bind"
_CAPTURING = "Press a key…"
_ESCAPE_KEY = Qt.Key.Key_Escape


class QKeyCaptureWidget(QPushButton):
    """A button that captures a keyboard shortcut when clicked.

    Idle: shows the current binding or ``"— Click to bind"``.
    Active: shows ``"Press a key…"``; any key+modifier emits and exits;
    Escape cancels capture.
    """

    binding_captured = Signal(object)  # KeyBinding

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent=parent)
        self._binding: KeyBinding | None = None
        self._capturing = False
        self._update_text()
        self.clicked.connect(self._enter_capture)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------

    def binding(self) -> KeyBinding | None:
        return self._binding

    def set_binding(self, b: KeyBinding | None) -> None:
        self._binding = b
        if self._capturing:
            self._capturing = False
            self.releaseKeyboard()
        self._update_text()

    # ------------------------------------------------------------------

    def _enter_capture(self) -> None:
        if self._capturing:
            return
        self._capturing = True
        self.setText(_CAPTURING)
        self.grabKeyboard()

    def _exit_capture(self, binding: KeyBinding | None = None) -> None:
        self._capturing = False
        self.releaseKeyboard()
        if binding is not None:
            self._binding = binding
            self.binding_captured.emit(binding)
        self._update_text()

    def _update_text(self) -> None:
        if self._binding is not None:
            self.setText(self._binding.key)
        else:
            self.setText(_PLACEHOLDER)

    # ------------------------------------------------------------------

    # type: ignore[override]
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == _ESCAPE_KEY:
            self._exit_capture(None)
            return

        # Ignore bare modifier presses
        if key in (
            Qt.Key.Key_Shift,
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        seq = QKeySequence(event.keyCombination())
        text = seq.toString(QKeySequence.SequenceFormat.PortableText)
        if text:
            self._exit_capture(KeyBinding(key=text))


__all__ = ["QKeyCaptureWidget"]
