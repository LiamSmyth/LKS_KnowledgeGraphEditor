"""Drag-enabled spinbox widgets for PySide6.

Spinbox widgets that support click-and-drag to adjust values:
- Click and drag up to increase value
- Click and drag down to decrease value
- Sensitivity adjustable via drag_sensitivity parameter
- Compatible with standard QSpinBox/QDoubleSpinBox API

Example:
    from lks_utils.gui_qt.widgets import DragSpinBox, DragDoubleSpinBox
    
    # Integer spinbox with drag
    int_spin = DragSpinBox()
    int_spin.setRange(0, 100)
    int_spin.setValue(50)
    int_spin.setSingleStep(1)
    int_spin.setDragSensitivity(0.5)  # Slower drag
    
    # Float spinbox with drag
    float_spin = DragDoubleSpinBox()
    float_spin.setRange(0.0, 1.0)
    float_spin.setValue(0.5)
    float_spin.setSingleStep(0.01)
    float_spin.setDecimals(3)
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


from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


class DragSpinBox(QSpinBox):
    """QSpinBox with click-and-drag support for adjusting values.

    Click and drag vertically to increase (up) or decrease (down) the value.
    Drag sensitivity controls how many pixels of movement equal one step.

    Attributes:
        drag_sensitivity: Pixels per step (default 5.0)
        drag_enabled: Whether dragging is enabled (default True)
    """

    def __init__(self, parent: Any = None) -> None:
        """Initialize drag-enabled spinbox.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self._dragging: bool = False
        self._drag_start_pos: QPoint | None = None
        self._drag_start_value: int = 0
        self._accumulated_delta: float = 0.0
        self._drag_threshold: int = 3  # Pixels to move before activating drag
        self._potential_drag: bool = False
        self.drag_sensitivity: float = 5.0  # Pixels per step
        self.drag_enabled: bool = True

        # Visual feedback during drag
        self.setMouseTracking(True)

    def setDragSensitivity(self, sensitivity: float) -> None:
        """Set drag sensitivity (pixels per step).

        Args:
            sensitivity: Number of pixels to drag for one step increment.
                        Higher = less sensitive (need to drag more).
                        Lower = more sensitive (drag less for same change).
        """
        self.drag_sensitivity = max(0.1, sensitivity)

    def setDragEnabled(self, enabled: bool) -> None:
        """Enable or disable drag functionality.

        Args:
            enabled: Whether to enable drag mode
        """
        self.drag_enabled = enabled

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to start potential drag.

        Args:
            event: Mouse event
        """
        if (self.drag_enabled and
            event.button() == Qt.MouseButton.LeftButton and
                not self.isReadOnly()):

            # Start tracking for potential drag (from anywhere in spinbox)
            self._potential_drag = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_value = self.value()
            self._accumulated_delta = 0.0
            event.accept()
            return

        # Default behavior for button clicks or when drag disabled
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to adjust value during drag.

        Args:
            event: Mouse event
        """
        if self._drag_start_pos is not None:
            current_pos: QPoint = event.globalPosition().toPoint()
            delta_y: int = self._drag_start_pos.y() - current_pos.y()  # Up is positive

            # Check if we've moved enough to activate drag mode
            if self._potential_drag and abs(delta_y) >= self._drag_threshold:
                self._potential_drag = False
                self._dragging = True
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                # Prevent text selection
                self.lineEdit().deselect()

            if self._dragging:
                # Accumulate fractional steps
                self._accumulated_delta += delta_y / self.drag_sensitivity

                # Calculate number of steps
                steps: int = int(self._accumulated_delta)

                if steps != 0:
                    # Apply steps and update accumulated delta
                    new_value: int = self._drag_start_value + \
                        (steps * self.singleStep())
                    self.setValue(new_value)

                    # Keep fractional remainder
                    self._accumulated_delta -= steps

                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to end drag.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                # End drag mode
                self._dragging = False
                self._potential_drag = False
                self._drag_start_pos = None
                self._accumulated_delta = 0.0
                self.unsetCursor()
                event.accept()
                return
            elif self._potential_drag:
                # Was potential drag but never activated (normal click)
                self._potential_drag = False
                self._drag_start_pos = None
                # Let normal click behavior proceed

        super().mouseReleaseEvent(event)


class DragDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox with click-and-drag support for adjusting values.

    Click and drag vertically to increase (up) or decrease (down) the value.
    Drag sensitivity controls how many pixels of movement equal one step.

    Attributes:
        drag_sensitivity: Pixels per step (default 5.0)
        drag_enabled: Whether dragging is enabled (default True)
    """

    def __init__(self, parent: Any = None) -> None:
        """Initialize drag-enabled double spinbox.

        Args:
            parent: Parent widget
        """
        super().__init__(parent)

        self._dragging: bool = False
        self._drag_start_pos: QPoint | None = None
        self._drag_start_value: float = 0.0
        self._accumulated_delta: float = 0.0
        self._drag_threshold: int = 3  # Pixels to move before activating drag
        self._potential_drag: bool = False
        self.drag_sensitivity: float = 5.0  # Pixels per step
        self.drag_enabled: bool = True

        # Visual feedback during drag
        self.setMouseTracking(True)

    def setDragSensitivity(self, sensitivity: float) -> None:
        """Set drag sensitivity (pixels per step).

        Args:
            sensitivity: Number of pixels to drag for one step increment.
                        Higher = less sensitive (need to drag more).
                        Lower = more sensitive (drag less for same change).
        """
        self.drag_sensitivity = max(0.1, sensitivity)

    def setDragEnabled(self, enabled: bool) -> None:
        """Enable or disable drag functionality.

        Args:
            enabled: Whether to enable drag mode
        """
        self.drag_enabled = enabled

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press to start potential drag.

        Args:
            event: Mouse event
        """
        if (self.drag_enabled and
            event.button() == Qt.MouseButton.LeftButton and
                not self.isReadOnly()):

            # Start tracking for potential drag (from anywhere in spinbox)
            self._potential_drag = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_start_value = self.value()
            self._accumulated_delta = 0.0
            event.accept()
            return

        # Default behavior for button clicks or when drag disabled
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move to adjust value during drag.

        Args:
            event: Mouse event
        """
        if self._drag_start_pos is not None:
            current_pos: QPoint = event.globalPosition().toPoint()
            delta_y: int = self._drag_start_pos.y() - current_pos.y()  # Up is positive

            # Check if we've moved enough to activate drag mode
            if self._potential_drag and abs(delta_y) >= self._drag_threshold:
                self._potential_drag = False
                self._dragging = True
                self.setCursor(Qt.CursorShape.SizeVerCursor)
                # Prevent text selection
                self.lineEdit().deselect()

            if self._dragging:
                # Accumulate fractional steps
                self._accumulated_delta += delta_y / self.drag_sensitivity

                # Calculate number of steps (keep as float for smooth adjustment)
                steps: float = self._accumulated_delta

                if abs(steps) >= 1.0:
                    # Apply steps and update accumulated delta
                    new_value: float = self._drag_start_value + \
                        (steps * self.singleStep())
                    self.setValue(new_value)

                    # Keep fractional remainder
                    self._accumulated_delta -= int(steps)

                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to end drag.

        Args:
            event: Mouse event
        """
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                # End drag mode
                self._dragging = False
                self._potential_drag = False
                self._drag_start_pos = None
                self._accumulated_delta = 0.0
                self.unsetCursor()
                event.accept()
                return
            elif self._potential_drag:
                # Was potential drag but never activated (normal click)
                self._potential_drag = False
                self._drag_start_pos = None
                # Let normal click behavior proceed

        super().mouseReleaseEvent(event)
