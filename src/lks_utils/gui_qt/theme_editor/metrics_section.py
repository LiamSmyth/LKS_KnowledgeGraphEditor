"""QMetricsSection — reflective editor for a Metrics dataclass."""
from __future__ import annotations

import dataclasses

from lks_utils.theme.metrics import Metrics

from PySide6.QtWidgets import (
    QWidget,
    QFormLayout,
    QSpinBox,
    QScrollArea,
    QVBoxLayout,
)
from PySide6.QtCore import Signal

# Pixel fields use a tighter range; spacing fields allow slightly more
_PIXEL_RANGE = (1, 64)
_SPACING_RANGE = (0, 64)


def _range_for(field_name: str) -> tuple[int, int]:
    if "spacing" in field_name:
        return _SPACING_RANGE
    return _PIXEL_RANGE


class QMetricsSection(QWidget):
    """Reflective editor for all Metrics integer-pixel fields."""

    metrics_changed = Signal(object)  # Metrics

    def __init__(
        self,
        metrics: Metrics,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._metrics = metrics
        self._spinboxes: dict[str, QSpinBox] = {}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        form = QFormLayout(inner)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(4)

        for field in dataclasses.fields(metrics):
            spin = QSpinBox()
            lo, hi = _range_for(field.name)
            spin.setRange(lo, hi)
            spin.setValue(getattr(metrics, field.name))
            spin.valueChanged.connect(
                lambda val, fn=field.name: self._on_spin_changed(fn, val)
            )
            self._spinboxes[field.name] = spin
            form.addRow(field.name, spin)

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------

    def metrics(self) -> Metrics:
        return self._metrics

    def set_metrics(self, metrics: Metrics) -> None:
        self._metrics = metrics
        for field_name, spin in self._spinboxes.items():
            spin.blockSignals(True)
            spin.setValue(getattr(metrics, field_name))
            spin.blockSignals(False)

    # ------------------------------------------------------------------

    def _on_spin_changed(self, field_name: str, value: int) -> None:
        self._metrics = dataclasses.replace(
            self._metrics, **{field_name: value})
        self.metrics_changed.emit(self._metrics)


__all__ = ["QMetricsSection"]
