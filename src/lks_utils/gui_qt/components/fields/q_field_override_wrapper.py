"""Reusable Unreal-style override wrapper for typed field widgets."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QSizePolicy, QWidget

from lks_utils.gui_qt.theme.palette import PALETTE


class QFieldOverrideWrapper(QWidget):
    """Wrap a field with a left override checkbox that gates editability."""

    override_changed = Signal(bool)
    override_cleared = Signal()
    value_changed = Signal(object)
    committed = Signal(object)

    def __init__(
        self,
        field_widget: QWidget,
        *,
        overridden: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._field_widget = field_widget

        self._override_checkbox = QCheckBox(self)
        self._override_checkbox.setObjectName("field_override_checkbox")
        self._override_checkbox.setToolTip("Override inherited value")
        self._override_checkbox.setChecked(overridden)
        self._override_checkbox.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._override_checkbox.setStyleSheet(
            "QCheckBox {"
            " padding: 0; margin: 0 2px 0 0;"
            f" color: {PALETTE['selection_marquee']};"
            "}"
            "QCheckBox::indicator {"
            " width: 14px; height: 14px;"
            "}"
            "QCheckBox::indicator:unchecked {"
            f" border: 1px solid {PALETTE['canvas_border']};"
            f" background: {PALETTE['canvas_bg']};"
            "}"
            "QCheckBox::indicator:checked {"
            f" border: 1px solid {PALETTE['selection_marquee']};"
            f" background: {PALETTE['layer_row_active']};"
            "}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._override_checkbox, 0)
        layout.addWidget(self._field_widget, 1)

        self._override_checkbox.toggled.connect(self._on_override_toggled)
        self._forward_field_signals()
        self._apply_override_state(overridden)

    def field_widget(self) -> QWidget:
        """Return the wrapped field widget."""
        return self._field_widget

    def is_overridden(self) -> bool:
        """Return whether this row currently overrides inherited value."""
        return self._override_checkbox.isChecked()

    def set_overridden(self, overridden: bool) -> None:
        """Set override state programmatically."""
        self._override_checkbox.setChecked(overridden)

    def set_override_tooltip(self, tooltip: str) -> None:
        """Set tooltip text on wrapper and override checkbox."""
        self.setToolTip(tooltip)
        self._override_checkbox.setToolTip(tooltip)

    def value(self) -> Any:
        """Return current field value when the child supports a value API."""
        getter = getattr(self._field_widget, "value", None)
        if callable(getter):
            return getter()
        return None

    def _on_override_toggled(self, overridden: bool) -> None:
        self._apply_override_state(overridden)
        self.override_changed.emit(overridden)
        if not overridden:
            self.override_cleared.emit()

    def _apply_override_state(self, overridden: bool) -> None:
        setter = getattr(self._field_widget, "set_editable", None)
        if callable(setter):
            setter(overridden)
        self._field_widget.setEnabled(overridden)

    def _forward_field_signals(self) -> None:
        value_signal = getattr(self._field_widget, "value_changed", None)
        if value_signal is not None:
            value_signal.connect(self.value_changed.emit)
        commit_signal = getattr(self._field_widget, "committed", None)
        if commit_signal is not None:
            commit_signal.connect(self._on_field_committed)

    def _on_field_committed(self, *args: object) -> None:
        """Forward child commit payloads with backward-compatible arity.

        Some fields emit ``committed(value, reason)`` while others emit
        ``committed(value)``. This wrapper normalizes to ``committed(value)``.
        """
        if args:
            self.committed.emit(args[0])
            return
        self.committed.emit(self.value())


__all__ = ["QFieldOverrideWrapper"]
