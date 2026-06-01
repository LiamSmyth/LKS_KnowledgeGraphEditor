"""QActionRowWidget — one row per Action in the bindings editor."""
from __future__ import annotations

from lks_utils.input.action import Action
from lks_utils.input.binding import Binding, KeyBinding, MouseBinding, WheelBinding
from lks_utils.gui_qt.bindings_editor.key_capture_widget import QKeyCaptureWidget
from lks_utils.gui_qt.bindings_editor.mouse_capture_widget import QMouseCaptureWidget
from lks_utils.gui_qt.bindings_editor.wheel_capture_widget import QWheelCaptureWidget

from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QMenu,
    QFrame,
)
from PySide6.QtCore import Signal, Qt


def _binding_label(b: Binding) -> str:
    if isinstance(b, KeyBinding):
        return b.key
    if isinstance(b, MouseBinding):
        mods = "+".join(m.value.capitalize()
                        for m in sorted(b.modifiers, key=lambda m: m.value))
        parts = [mods] if mods else []
        parts.append(b.button.value.capitalize())
        parts.append(b.gesture.value.replace("_", "-").capitalize())
        return "+".join(parts)
    if isinstance(b, WheelBinding):
        mods = "+".join(m.value.capitalize()
                        for m in sorted(b.modifiers, key=lambda m: m.value))
        parts = [mods] if mods else []
        parts.append(f"Wheel({b.direction})")
        return "+".join(parts)
    return str(b)


class _BindingRow(QWidget):
    """One capture widget + delete button."""

    removed = Signal(object)  # this widget
    changed = Signal(object)  # Binding

    def __init__(self, binding: Binding, *, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent)
        self._binding = binding

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if isinstance(binding, KeyBinding):
            w = QKeyCaptureWidget()
            w.set_binding(binding)
            w.binding_captured.connect(self._on_key)
            self._capture_widget = w
        elif isinstance(binding, MouseBinding):
            w = QMouseCaptureWidget(binding)
            w.binding_changed.connect(self._on_binding)
            self._capture_widget = w
        else:  # WheelBinding
            w = QWheelCaptureWidget(binding)
            w.binding_changed.connect(self._on_binding)
            self._capture_widget = w

        layout.addWidget(self._capture_widget, stretch=1)

        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(24)
        btn_del.setToolTip("Remove this binding")
        btn_del.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(btn_del)

    def current_binding(self) -> Binding:
        if isinstance(self._capture_widget, QKeyCaptureWidget):
            return self._capture_widget.binding() or self._binding
        if isinstance(self._capture_widget, QMouseCaptureWidget):
            return self._capture_widget.binding()
        return self._capture_widget.binding()

    def _on_key(self, b: KeyBinding) -> None:
        self._binding = b
        self.changed.emit(b)

    def _on_binding(self, b: Binding) -> None:
        self._binding = b
        self.changed.emit(b)


class QActionRowWidget(QWidget):
    """One row in the bindings editor: scope tag + name + description + bindings."""

    binding_changed = Signal(object, list)  # (Action, list[Binding])

    def __init__(
        self,
        action: Action,
        bindings: list[Binding],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._action = action
        self._bindings: list[Binding] = list(bindings)
        self._rows: list[_BindingRow] = []
        self._build_ui()

    # ------------------------------------------------------------------

    def action(self) -> Action:
        return self._action

    def bindings(self) -> list[Binding]:
        return [r.current_binding() for r in self._rows]

    def set_bindings(self, bindings: list[Binding]) -> None:
        self._bindings = list(bindings)
        self._rebuild_rows()

    def set_conflict(self, conflicting_with: Action | None) -> None:
        if conflicting_with is not None:
            self.setStyleSheet("border: 1px solid red;")
            self.setToolTip(f"Conflicts with: {conflicting_with.label}")
        else:
            self.setStyleSheet("")
            self.setToolTip("")

    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(8)

        # Scope tag
        scope_lbl = QLabel(f"[{self._action.scope}]")
        scope_lbl.setFixedWidth(120)
        scope_lbl.setStyleSheet("color: gray; font-size: 10px;")
        root.addWidget(scope_lbl)

        # Name + description
        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        name_lbl = QLabel(self._action.label)
        name_lbl.setStyleSheet("font-weight: bold;")
        desc_lbl = QLabel(self._action.description)
        desc_lbl.setStyleSheet("color: gray; font-size: 10px;")
        desc_lbl.setWordWrap(True)
        name_col.addWidget(name_lbl)
        name_col.addWidget(desc_lbl)
        root.addLayout(name_col, stretch=1)

        # Bindings column
        bindings_col = QVBoxLayout()
        bindings_col.setSpacing(2)
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        self._rebuild_rows()
        bindings_col.addWidget(self._rows_container)

        btn_add = QPushButton("+ Add binding")
        btn_add.setFixedWidth(100)
        btn_add.clicked.connect(self._add_binding_menu)
        bindings_col.addWidget(btn_add)
        root.addLayout(bindings_col)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)

    def _rebuild_rows(self) -> None:
        # Clear existing rows
        for row in self._rows:
            row.setParent(None)
        self._rows.clear()

        for b in self._bindings:
            row = _BindingRow(b)
            row.removed.connect(self._remove_row)
            row.changed.connect(lambda _: self._emit_changed())
            self._rows.append(row)
            self._rows_layout.addWidget(row)

    def _remove_row(self, row: _BindingRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            row.setParent(None)
            self._emit_changed()

    def _add_binding_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction(
            "Keyboard", lambda: self._add_default(KeyBinding(key="?")))
        menu.addAction("Mouse", lambda: self._add_default(
            MouseBinding(button=__import__("lks_utils.input.binding",
                         fromlist=["MouseButton"]).MouseButton.LEFT)
        ))
        menu.addAction("Wheel", lambda: self._add_default(WheelBinding()))
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _add_default(self, binding: Binding) -> None:
        self._bindings.append(binding)
        row = _BindingRow(binding)
        row.removed.connect(self._remove_row)
        row.changed.connect(lambda _: self._emit_changed())
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._emit_changed()

    def _emit_changed(self) -> None:
        self.binding_changed.emit(self._action, self.bindings())


__all__ = ["QActionRowWidget"]
