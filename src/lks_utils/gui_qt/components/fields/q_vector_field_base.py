"""Base class for compact fixed-dimension vector fields."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QSizePolicy,
    QWidget,
)

from lks_utils.gui_qt.components.fields.field_validation_result import FieldValidationResult
from lks_utils.gui_qt.components.fields.q_field_base import QFieldBase


class _VectorEditor(QWidget):
    """Composite row of spin boxes for a fixed-length vector."""

    # One shared preferred width across all vector dimensions so stacked rows line up.
    _GLOBAL_COMPONENT_WIDTH: int = 86
    _MIN_COMPONENT_WIDTH: int = 1

    value_changed = Signal()

    def __init__(self, dimension: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._boxes: list[QDoubleSpinBox] = []
        self._dimension = dimension

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for _index in range(dimension):
            box = QDoubleSpinBox(self)
            box.setRange(-1.0e12, 1.0e12)
            box.setDecimals(6)
            box.setSingleStep(0.1)
            box.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            box.setAlignment(Qt.AlignmentFlag.AlignRight)
            box.setFixedHeight(24)
            box.setMinimumWidth(self._MIN_COMPONENT_WIDTH)
            box.setSizePolicy(QSizePolicy.Policy.Fixed,
                              QSizePolicy.Policy.Fixed)
            box.valueChanged.connect(self._on_component_changed)
            self._boxes.append(box)
            layout.addWidget(box, 1)

        layout.addStretch(1)
        self._sync_component_widths()

    def install_field_event_filter(self, event_filter: QObject) -> None:
        for box in self._boxes:
            box.installEventFilter(event_filter)

    def value(self) -> tuple[float, ...]:
        return tuple(box.value() for box in self._boxes)

    def set_value(self, value: Sequence[float]) -> None:
        values = list(value)
        if len(values) != self._dimension:
            raise ValueError(
                f"Expected {self._dimension} values, got {len(values)}")
        for index, box in enumerate(self._boxes):
            box.setValue(float(values[index]))

    def set_editable(self, editable: bool) -> None:
        for box in self._boxes:
            box.setEnabled(editable)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._sync_component_widths()

    def _on_component_changed(self) -> None:
        self.value_changed.emit()

    def _sync_component_widths(self) -> None:
        if not self._boxes:
            return
        spacing = self.layout().spacing() if self.layout() is not None else 4
        available = max(0, self.contentsRect().width() -
                        spacing * (len(self._boxes) - 1))
        preferred_total = self._GLOBAL_COMPONENT_WIDTH * len(self._boxes)
        if available >= preferred_total:
            target_width = self._GLOBAL_COMPONENT_WIDTH
        else:
            # When clipped, rescale every component evenly to fit the current width.
            target_width = max(self._MIN_COMPONENT_WIDTH,
                               available // len(self._boxes))
        for box in self._boxes:
            box.setFixedWidth(target_width)


class QVectorFieldBase(QFieldBase):
    """Field widget for a fixed-length vector of floats."""

    COMPONENT_COUNT: int = 2

    def __init__(
        self,
        default_value: Sequence[float],
        *,
        vector_size: int,
        parent: QWidget | None = None,
    ) -> None:
        if vector_size <= 0:
            raise ValueError("vector_size must be a positive integer")
        self._vector_size = vector_size
        normalized = self._coerce_vector(default_value)
        if normalized is None:
            raise ValueError(
                f"Expected {self._vector_size} numeric values for {type(self).__name__}")
        super().__init__(normalized, parent=parent)

    def _create_editor(self) -> QWidget:
        return _VectorEditor(self._vector_size, parent=self)

    def _connect_editor_signals(self) -> None:
        editor = self._editor
        assert isinstance(editor, _VectorEditor)
        editor.install_field_event_filter(self)
        editor.value_changed.connect(self._on_components_changed)

    def _on_components_changed(self) -> None:
        self._on_editor_value_changed(self._read_editor_value())

    def _read_editor_value(self) -> Any:
        editor = self._editor
        assert isinstance(editor, _VectorEditor)
        return editor.value()

    def _write_editor_value(self, value: Any) -> None:
        editor = self._editor
        assert isinstance(editor, _VectorEditor)
        vector = self._coerce_vector(value)
        if vector is None:
            vector = self._default_value
        editor.set_value(vector)

    def _set_editor_editable(self, editable: bool) -> None:
        editor = self._editor
        assert isinstance(editor, _VectorEditor)
        editor.set_editable(editable)

    def validate_value(self, value: Any) -> FieldValidationResult:
        vector = self._coerce_vector(value)
        if vector is None:
            return FieldValidationResult(
                is_valid=False,
                message=f"Enter exactly {self._vector_size} numeric values.",
            )
        return FieldValidationResult(is_valid=True, normalized_value=vector)

    def _coerce_vector(self, value: Any) -> tuple[float, ...] | None:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            return None
        items = list(value)
        if len(items) != self._vector_size:
            return None
        try:
            return tuple(float(item) for item in items)
        except (TypeError, ValueError):
            return None


__all__ = ["QVectorFieldBase"]
