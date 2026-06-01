"""Labeled spinbox component (PySide6).

A reusable UI component combining:
- Label (e.g., "Max Dimension:")
- Spinbox with numeric input (optionally drag-enabled)
- Optional unit label (e.g., "px", "MB", "%")
- Optional tooltip

Example:
    from lks_utils.gui_qt.components import QLabeledSpinboxComponent
    
    # Basic usage
    max_dim = QLabeledSpinboxComponent(
        parent,
        label="Max Dimension:",
        from_=100, to=7680, increment=100,
        default=1920,
        unit="px",
        tooltip="Maximum dimension for output images"
    )
    
    # With drag support
    quality = QLabeledSpinboxComponent(
        parent,
        label="Quality:",
        from_=0, to=100,
        drag_enabled=True,
        drag_sensitivity=3.0,
        tooltip="Click and drag to adjust"
    )
    
    # Get/set value
    value = max_dim.get_value()
    max_dim.set_value(3840)
    
    # State persistence
    state = max_dim.to_dict()
    max_dim.from_dict(state)
"""

from __future__ import annotations
import sys
# Initialize COM before Qt imports on Windows (clipboard requires apartment-threaded mode)
if sys.platform == "win32":
    try:
        import ctypes
        # Try apartment-threaded mode first for clipboard compatibility
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


from typing import Any, Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from lks_utils.gui_qt.widgets import DragDoubleSpinBox, DragSpinBox


class QLabeledSpinboxComponent(QWidget):
    """Spinbox with label, unit, and tooltip.

    Provides a consistent UI pattern for numeric input across GUIs.
    Optionally supports drag mode for click-and-drag value adjustment.

    Signals:
        value_changed: Emitted when value changes with new value (int or float)
    """

    value_changed = Signal(object)  # Can be int or float

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "",
        from_: float = 0,
        to: float = 100,
        increment: float = 1,
        default: float | None = None,
        unit: str = "",
        tooltip: str = "",
        on_change: Callable[[float], None] | None = None,
        spinbox_width: int = 10,
        is_float: bool = False,
        drag_enabled: bool = False,
        drag_sensitivity: float = 5.0,
    ) -> None:
        """Initialize the labeled spinbox component.

        Args:
            parent: Parent widget
            label: Label text (shown before spinbox)
            from_: Minimum value
            to: Maximum value
            increment: Step increment
            default: Default value (uses from_ if not specified)
            unit: Unit label (shown after spinbox, e.g., "px", "MB")
            tooltip: Tooltip text for the spinbox
            on_change: Callback when value changes, receives new value
            spinbox_width: Width of spinbox in characters
            is_float: If True, uses QDoubleSpinBox; if False, uses QSpinBox
            drag_enabled: If True, enables click-and-drag value adjustment
            drag_sensitivity: Pixels per step when dragging (higher = slower)
        """
        super().__init__(parent)

        self.on_change = on_change
        self.is_float = is_float
        self.from_ = from_
        self.to = to
        self.drag_enabled = drag_enabled

        self._build_ui(label, unit, tooltip, spinbox_width,
                       from_, to, increment, default, drag_sensitivity)

        # Connect change handler
        if on_change:
            self.value_changed.connect(on_change)

    def _build_ui(
        self,
        label: str,
        unit: str,
        tooltip: str,
        spinbox_width: int,
        from_: float,
        to: float,
        increment: float,
        default: float | None,
        drag_sensitivity: float,
    ) -> None:
        """Build the component UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Label (optional)
        if label:
            self._label = QLabel(label)
            layout.addWidget(self._label)
        else:
            self._label = None

        # Spinbox (int or float, drag or standard)
        if self.is_float:
            if self.drag_enabled:
                self._spinbox = DragDoubleSpinBox()
                self._spinbox.setDragSensitivity(drag_sensitivity)
            else:
                self._spinbox = QDoubleSpinBox()
            self._spinbox.setDecimals(2)
            self._spinbox.setMinimum(from_)
            self._spinbox.setMaximum(to)
            self._spinbox.setSingleStep(increment)
            self._spinbox.setValue(default if default is not None else from_)
            self._spinbox.valueChanged.connect(self._on_spinbox_changed)
        else:
            if self.drag_enabled:
                self._spinbox = DragSpinBox()
                self._spinbox.setDragSensitivity(drag_sensitivity)
            else:
                self._spinbox = QSpinBox()
            self._spinbox.setMinimum(int(from_))
            self._spinbox.setMaximum(int(to))
            self._spinbox.setSingleStep(int(increment))
            self._spinbox.setValue(
                int(default if default is not None else from_))
            self._spinbox.valueChanged.connect(self._on_spinbox_changed)

        # Calculate width in pixels (rough approximation: 7px per char)
        spinbox_width_px: int = spinbox_width * 7
        self._spinbox.setMinimumWidth(spinbox_width_px)

        if tooltip:
            self._spinbox.setToolTip(tooltip)

        layout.addWidget(self._spinbox)

        # Unit label (optional)
        if unit:
            self._unit_label = QLabel(unit)
            layout.addWidget(self._unit_label)
        else:
            self._unit_label = None

    def _on_spinbox_changed(self, value: int | float) -> None:
        """Handle spinbox value change."""
        # Value is already clamped by QSpinBox/QDoubleSpinBox
        self.value_changed.emit(value)

    def get_value(self) -> float | int:
        """Get the current value.

        Returns:
            Current numeric value (int or float based on is_float)
        """
        if self.is_float:
            return self._spinbox.value()
        else:
            return int(self._spinbox.value())

    def set_value(self, value: float | int) -> None:
        """Set the value.

        Args:
            value: Numeric value to set (clamped to valid range)
        """
        # QSpinBox/QDoubleSpinBox will automatically clamp
        if self.is_float:
            self._spinbox.setValue(float(value))
        else:
            self._spinbox.setValue(int(value))

    def to_dict(self) -> dict[str, Any]:
        """Serialize component state to dict for persistence.

        Returns:
            Dictionary with value state
        """
        return {
            "value": self.get_value(),
        }

    def from_dict(self, state: dict[str, Any]) -> None:
        """Restore component state from dict.

        Args:
            state: Dictionary with value state
        """
        if "value" in state:
            self.set_value(state["value"])

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: True to enable, False to disable
        """
        self._spinbox.setEnabled(enabled)

    def set_drag_enabled(self, enabled: bool) -> None:
        """Enable or disable drag mode (if spinbox supports it).

        Args:
            enabled: True to enable drag, False to disable
        """
        if hasattr(self._spinbox, 'setDragEnabled'):
            self._spinbox.setDragEnabled(enabled)

    def set_drag_sensitivity(self, sensitivity: float) -> None:
        """Set drag sensitivity (if spinbox supports it).

        Args:
            sensitivity: Pixels per step (higher = slower dragging)
        """
        if hasattr(self._spinbox, 'setDragSensitivity'):
            self._spinbox.setDragSensitivity(sensitivity)

    def set_range(self, from_: float, to: float) -> None:
        """Update the valid range.

        Args:
            from_: New minimum value
            to: New maximum value
        """
        self.from_ = from_
        self.to = to

        if self.is_float:
            self._spinbox.setMinimum(from_)
            self._spinbox.setMaximum(to)
        else:
            self._spinbox.setMinimum(int(from_))
            self._spinbox.setMaximum(int(to))

        # Clamp current value to new range (Qt handles this automatically)
