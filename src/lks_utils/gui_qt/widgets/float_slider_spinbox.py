"""QFloatSliderSpinBox — horizontal slider linked bidirectionally to a QDoubleSpinBox."""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QStyle, QStyleOptionSlider, QToolTip, QWidget

from lks_utils.gui_qt.widgets._modifier_slider import _ModifierSlider as _CtrlSnapSlider

# Number of slider integer ticks per one step unit.  The slider integer
# resolution is _FINE_SCALE_FACTOR times finer than the configured step so
# that free drag (no modifier held) gives smooth, continuous movement while
# Ctrl-snap still aligns exactly to step-sized increments.
_FINE_SCALE_FACTOR: int = 10


def _decimals_from_step(step: float) -> int:
    """Infer decimal places from a step value.

    Examples:
        step=0.01  → 2
        step=0.001 → 3
        step=0.1   → 1
        step=0.05  → 2
        step=1.0   → 0
    """
    if step <= 0:
        return 2
    return max(0, -int(math.floor(math.log10(step))))


class QFloatSliderSpinBox(QWidget):
    """A horizontal QSlider bidirectionally linked to a QDoubleSpinBox.

    The slider uses integer precision internally; the ``step`` size determines
    the integer resolution (scale = ``round(1 / step)``).  Both controls always
    reflect the same float value.  Emits ``value_changed(float)`` whenever the
    value changes from either control.

    **Standard mode** (``soft_range=False``, default)::

        [======slider======] [value_spinbox]

    **Soft-range mode** (``soft_range=True``)::

        [min_spinbox] [======slider======] [max_spinbox]

    In soft-range mode, the two spinboxes at either end define the slider range
    and are editable at runtime.  The slider selects a value between them.  The
    current value is shown as a tooltip on the slider.

    Modifier keys during slider drag:

    * **Ctrl**       — snap to 1/32 divisions of the current range.
    * **Shift**      — fine mode: the slider moves at 1/10 normal sensitivity.
    * **Ctrl+Shift** — fine movement constrained to snap grid points.

    Signals:
        value_changed(float): Emitted when the value changes from any source.

    Args:
        min_value: Minimum float value (or initial soft-range left bound).
        max_value: Maximum float value (or initial soft-range right bound).
        default_value: Initial value.
        step: Smallest increment; determines slider integer resolution.
        decimals: Decimal places shown in the spinbox.  Inferred from ``step``
            when ``None``.
        spinbox_width: Fixed width of the spinbox in pixels.
        tooltip: Tooltip shown on both the slider and spinbox.
        on_change: Optional callback receiving the new float value.
        soft_range: When ``True``, show editable min/max spinboxes instead of a
            single value spinbox.  The spinbox absolute limits default to
            ``soft_range_limits`` or ``(-1e6, 1e6)``.
        soft_range_limits: ``(abs_min, abs_max)`` — hard limits for the range
            spinboxes in soft-range mode.  Prevents extreme values.
        parent: Parent widget.

    Example (standard)::

        slider_spin = QFloatSliderSpinBox(
            min_value=0.01, max_value=20.0, default_value=1.0,
            step=0.01, tooltip="Displacement height multiplier"
        )

    Example (soft-range)::

        slider_spin = QFloatSliderSpinBox(
            min_value=0.0, max_value=1.0, default_value=0.5,
            step=0.01, soft_range=True,
            soft_range_limits=(-100.0, 100.0),
        )
    """

    value_changed = Signal(float)

    def __init__(
        self,
        *,
        min_value: float = 0.0,
        max_value: float = 1.0,
        default_value: float = 0.5,
        step: float = 0.01,
        decimals: int | None = None,
        spinbox_width: int = 72,
        tooltip: str = "",
        on_change: Callable[[float], None] | None = None,
        soft_range: bool = False,
        soft_range_limits: tuple[float, float] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._scale: int = max(1, round(1.0 / step) * _FINE_SCALE_FACTOR)
        self._step = step
        self._decimals: int = decimals if decimals is not None else _decimals_from_step(
            step)
        self._on_change = on_change
        self._blocked = False
        self._soft_range = soft_range

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if soft_range:
            self._build_soft_range(
                layout, min_value, max_value, default_value,
                spinbox_width, tooltip, soft_range_limits,
            )
        else:
            self._build_standard(
                layout, min_value, max_value, default_value,
                spinbox_width, tooltip,
            )

        # Configure Ctrl-snap to land exactly on step-sized increments.
        snap_step_int = max(1, round(step * self._scale))
        self._slider.set_snap_step_int(snap_step_int)

    # ------------------------------------------------------------------
    # Layout builders
    # ------------------------------------------------------------------

    def _build_standard(
        self,
        layout: QHBoxLayout,
        min_value: float,
        max_value: float,
        default_value: float,
        spinbox_width: int,
        tooltip: str,
    ) -> None:
        """Create ``[slider] [value_spinbox]`` layout."""
        self._slider = _CtrlSnapSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(
            round(min_value * self._scale),
            round(max_value * self._scale),
        )
        self._slider.setValue(round(default_value * self._scale))
        if tooltip:
            self._slider.setToolTip(tooltip)
        self._slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider, stretch=1)

        self._spinbox = QDoubleSpinBox()
        self._spinbox.setRange(min_value, max_value)
        self._spinbox.setValue(default_value)
        self._spinbox.setSingleStep(self._step)
        self._spinbox.setDecimals(self._decimals)
        self._spinbox.setFixedWidth(spinbox_width)
        if tooltip:
            self._spinbox.setToolTip(tooltip)
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)
        layout.addWidget(self._spinbox)

        # Not used in standard mode
        self._min_spinbox: QDoubleSpinBox | None = None
        self._max_spinbox: QDoubleSpinBox | None = None

    def _build_soft_range(
        self,
        layout: QHBoxLayout,
        min_value: float,
        max_value: float,
        default_value: float,
        spinbox_width: int,
        tooltip: str,
        soft_range_limits: tuple[float, float] | None,
    ) -> None:
        """Create ``[min_spinbox] [slider] [max_spinbox]`` layout."""
        abs_min, abs_max = soft_range_limits or (-1e6, 1e6)

        # ── Min spinbox (left) ────────────────────────────────────────
        self._min_spinbox = QDoubleSpinBox()
        self._min_spinbox.setRange(abs_min, abs_max)
        self._min_spinbox.setValue(min_value)
        self._min_spinbox.setSingleStep(self._step)
        self._min_spinbox.setDecimals(self._decimals)
        self._min_spinbox.setFixedWidth(spinbox_width)
        self._min_spinbox.setToolTip("Slider range minimum")
        self._min_spinbox.valueChanged.connect(self._on_range_spinbox_changed)
        layout.addWidget(self._min_spinbox)

        # ── Slider ────────────────────────────────────────────────────
        self._slider = _CtrlSnapSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(
            round(min_value * self._scale),
            round(max_value * self._scale),
        )
        self._slider.setValue(round(default_value * self._scale))
        if tooltip:
            self._slider.setToolTip(tooltip)
        self._slider.valueChanged.connect(self._on_slider_changed_soft)
        layout.addWidget(self._slider, stretch=1)

        # ── Max spinbox (right) ───────────────────────────────────────
        self._max_spinbox = QDoubleSpinBox()
        self._max_spinbox.setRange(abs_min, abs_max)
        self._max_spinbox.setValue(max_value)
        self._max_spinbox.setSingleStep(self._step)
        self._max_spinbox.setDecimals(self._decimals)
        self._max_spinbox.setFixedWidth(spinbox_width)
        self._max_spinbox.setToolTip("Slider range maximum")
        self._max_spinbox.valueChanged.connect(self._on_range_spinbox_changed)
        layout.addWidget(self._max_spinbox)

        # Not used in soft-range mode
        self._spinbox: QDoubleSpinBox | None = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_value(self) -> float:
        """Return the current float value."""
        return self._slider.value() / self._scale

    def set_value(self, value: float) -> None:
        """Set the slider to *value* without emitting ``value_changed``."""
        self._blocked = True
        self._slider.setValue(round(value * self._scale))
        if not self._soft_range and self._spinbox is not None:
            self._spinbox.setValue(value)
        self._blocked = False

    def set_range(self, min_value: float, max_value: float) -> None:
        """Update the slider and spinbox range.

        The current value is clamped to the new range automatically.
        """
        self._blocked = True
        self._slider.setRange(
            round(min_value * self._scale),
            round(max_value * self._scale),
        )
        if self._soft_range:
            if self._min_spinbox is not None:
                self._min_spinbox.setValue(min_value)
            if self._max_spinbox is not None:
                self._max_spinbox.setValue(max_value)
        elif self._spinbox is not None:
            self._spinbox.setRange(min_value, max_value)
        self._blocked = False

    def get_range(self) -> tuple[float, float]:
        """Return the current (min, max) of the slider."""
        return (
            self._slider.minimum() / self._scale,
            self._slider.maximum() / self._scale,
        )

    # ------------------------------------------------------------------
    # Standard-mode signal handlers
    # ------------------------------------------------------------------

    def _on_slider_changed(self, int_val: int) -> None:
        if self._blocked:
            return
        self._blocked = True
        float_val = int_val / self._scale
        self._spinbox.setValue(float_val)
        self._blocked = False
        self._show_handle_tooltip(float_val)
        self.value_changed.emit(float_val)
        if self._on_change is not None:
            self._on_change(float_val)

    def _on_spinbox_changed(self, float_val: float) -> None:
        if self._blocked:
            return
        self._blocked = True
        self._slider.setValue(round(float_val * self._scale))
        self._blocked = False
        self.value_changed.emit(float_val)
        if self._on_change is not None:
            self._on_change(float_val)

    # ------------------------------------------------------------------
    # Soft-range-mode signal handlers
    # ------------------------------------------------------------------

    def _on_slider_changed_soft(self, int_val: int) -> None:
        """Slider moved in soft-range mode — emit value."""
        if self._blocked:
            return
        float_val = int_val / self._scale
        self._show_handle_tooltip(float_val)
        self.value_changed.emit(float_val)
        if self._on_change is not None:
            self._on_change(float_val)

    def _show_handle_tooltip(self, value: float) -> None:
        """Show the current value as a QToolTip above the slider handle.

        Computes the handle rect via ``QStyleOptionSlider`` so the tip tracks
        the handle precisely during drag and on hover.
        """
        opt = QStyleOptionSlider()
        self._slider.initStyleOption(opt)
        handle_rect = self._slider.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            opt,
            QStyle.SubControl.SC_SliderHandle,
            self._slider,
        )
        tip_pos = self._slider.mapToGlobal(handle_rect.center())
        tip_pos.setY(tip_pos.y() - handle_rect.height() - 4)
        QToolTip.showText(tip_pos, f"{value:.{self._decimals}f}", self._slider)

    def _on_range_spinbox_changed(self, _value: float) -> None:
        """Min or max spinbox edited — update slider range, clamp value."""
        if self._blocked or self._min_spinbox is None or self._max_spinbox is None:
            return
        new_min = self._min_spinbox.value()
        new_max = self._max_spinbox.value()
        if new_min >= new_max:
            return  # ignore degenerate range while user is typing
        self._blocked = True
        old_val = self._slider.value() / self._scale
        self._slider.setRange(
            round(new_min * self._scale),
            round(new_max * self._scale),
        )
        # Clamp previous value to new range
        clamped = max(new_min, min(new_max, old_val))
        self._slider.setValue(round(clamped * self._scale))
        self._blocked = False
        # Emit if value actually changed after clamping
        if abs(clamped - old_val) > 1e-9:
            self.value_changed.emit(clamped)
            if self._on_change is not None:
                self._on_change(clamped)
