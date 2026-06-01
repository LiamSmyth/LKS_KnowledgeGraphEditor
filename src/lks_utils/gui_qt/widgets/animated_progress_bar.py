"""Animated progress bar widget with smooth tweening."""

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


from PySide6.QtWidgets import QProgressBar
from PySide6.QtCore import QPropertyAnimation, QEasingCurve


class QAnimatedProgressBar(QProgressBar):
    """Progress bar with smooth value transitions.

    Animates value changes over a configurable duration using Qt's property
    animation system. Provides professional "floating needle" behavior for
    audio meters, download progress, etc.
    """

    def __init__(
        self,
        parent=None,
        *,
        animation_duration_ms: int = 80,
        easing_curve: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    ) -> None:
        """Initialize animated progress bar.

        Args:
            parent: Parent widget
            animation_duration_ms: Animation duration in milliseconds (default: 80ms)
            easing_curve: Qt easing curve for animation (default: OutCubic for natural deceleration)
        """
        super().__init__(parent)

        self._animation = QPropertyAnimation(self, b"value")
        self._animation.setDuration(animation_duration_ms)
        self._animation.setEasingCurve(easing_curve)

    def setValueAnimated(self, value: int) -> None:
        """Set progress bar value with smooth animation.

        Args:
            value: Target value to animate to
        """
        self._animation.stop()
        self._animation.setStartValue(self.value())
        self._animation.setEndValue(value)
        self._animation.start()

    def setValueImmediate(self, value: int) -> None:
        """Set progress bar value immediately without animation.

        Args:
            value: Value to set
        """
        self._animation.stop()
        self.setValue(value)

    def setAnimationDuration(self, duration_ms: int) -> None:
        """Change animation duration.

        Args:
            duration_ms: New duration in milliseconds
        """
        self._animation.setDuration(duration_ms)

    def setEasingCurve(self, curve: QEasingCurve.Type) -> None:
        """Change easing curve.

        Args:
            curve: Qt easing curve type
        """
        self._animation.setEasingCurve(curve)

    def stopAnimation(self) -> None:
        """Stop any running animation."""
        self._animation.stop()
