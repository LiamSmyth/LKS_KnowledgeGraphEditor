"""Hyperparameter sliders component for LLM generation parameters."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from lks_utils.gui_qt.theme import COLORS
from lks_utils.gui_qt.widgets._modifier_slider import _ModifierSlider


class QHyperparameterSlidersComponent(QWidget):
    """Component for LLM hyperparameter controls (temperature, top_p, top_k).

    Features:
    - Temperature slider (0.0-2.0)
    - Top P slider (0.0-1.0)
    - Top K spinbox (1-100)
    - Value labels that update live
    - Tooltips explaining each parameter
    - Compact layout

    Signals:
    - temperature_changed: Emitted when temperature changes (value: float)
    - top_p_changed: Emitted when top_p changes (value: float)
    - top_k_changed: Emitted when top_k changes (value: int)
    """

    temperature_changed = Signal(float)
    top_p_changed = Signal(float)
    top_k_changed = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        show_temperature: bool = True,
        show_top_p: bool = True,
        show_top_k: bool = True,
        temperature_default: float = 0.7,
        top_p_default: float = 0.9,
        top_k_default: int = 40,
    ) -> None:
        """Initialize hyperparameter sliders.

        Args:
            parent: Parent widget
            show_temperature: Show temperature slider
            show_top_p: Show top_p slider
            show_top_k: Show top_k spinbox
            temperature_default: Default temperature value
            top_p_default: Default top_p value
            top_k_default: Default top_k value
        """
        super().__init__(parent)

        self._show_temp = show_temperature
        self._show_p = show_top_p
        self._show_k = show_top_k

        self._temp_default = temperature_default
        self._p_default = top_p_default
        self._k_default = top_k_default

        # Widgets
        self._temp_slider: _ModifierSlider | None = None
        self._temp_label: QLabel | None = None
        self._p_slider: _ModifierSlider | None = None
        self._p_label: QLabel | None = None
        self._k_spinbox: QSpinBox | None = None

        # Build UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the component UI."""
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- Temperature ---
        if self._show_temp:
            temp_row = QWidget()
            temp_layout = QHBoxLayout(temp_row)
            temp_layout.setContentsMargins(0, 0, 0, 0)

            self._temp_slider = _ModifierSlider(Qt.Horizontal)
            self._temp_slider.setMinimum(0)
            self._temp_slider.setMaximum(200)  # 0.0 to 2.0, step 0.01
            self._temp_slider.setValue(int(self._temp_default * 100))
            self._temp_slider.setToolTip(
                "Controls randomness in generation.\n"
                "0.0 = Deterministic, focused\n"
                "0.7 = Balanced (recommended)\n"
                "1.5+ = Creative, varied"
            )
            self._temp_slider.valueChanged.connect(self._on_temp_changed)
            temp_layout.addWidget(self._temp_slider, stretch=1)

            self._temp_label = QLabel(f"{self._temp_default:.2f}")
            self._temp_label.setMinimumWidth(40)
            self._temp_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            temp_layout.addWidget(self._temp_label)

            layout.addRow("Temperature:", temp_row)

        # --- Top P ---
        if self._show_p:
            p_row = QWidget()
            p_layout = QHBoxLayout(p_row)
            p_layout.setContentsMargins(0, 0, 0, 0)

            self._p_slider = _ModifierSlider(Qt.Horizontal)
            self._p_slider.setMinimum(0)
            self._p_slider.setMaximum(100)  # 0.0 to 1.0, step 0.01
            self._p_slider.setValue(int(self._p_default * 100))
            self._p_slider.setToolTip(
                "Nucleus sampling threshold.\n"
                "Considers only top tokens with cumulative probability <= top_p.\n"
                "0.9 = Balanced (recommended)\n"
                "1.0 = Consider all tokens"
            )
            self._p_slider.valueChanged.connect(self._on_p_changed)
            p_layout.addWidget(self._p_slider, stretch=1)

            self._p_label = QLabel(f"{self._p_default:.2f}")
            self._p_label.setMinimumWidth(40)
            self._p_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            p_layout.addWidget(self._p_label)

            layout.addRow("Top P:", p_row)

        # --- Top K ---
        if self._show_k:
            self._k_spinbox = QSpinBox()
            self._k_spinbox.setMinimum(1)
            self._k_spinbox.setMaximum(100)
            self._k_spinbox.setValue(self._k_default)
            self._k_spinbox.setToolTip(
                "Number of highest probability tokens to consider.\n"
                "40 = Balanced (recommended)\n"
                "Lower = More focused\n"
                "Higher = More diverse"
            )
            self._k_spinbox.valueChanged.connect(self._on_k_changed)

            layout.addRow("Top K:", self._k_spinbox)

    def _on_temp_changed(self, value: int) -> None:
        """Handle temperature slider change."""
        temp = value / 100.0
        if self._temp_label:
            self._temp_label.setText(f"{temp:.2f}")
        self.temperature_changed.emit(temp)

    def _on_p_changed(self, value: int) -> None:
        """Handle top_p slider change."""
        p = value / 100.0
        if self._p_label:
            self._p_label.setText(f"{p:.2f}")
        self.top_p_changed.emit(p)

    def _on_k_changed(self, value: int) -> None:
        """Handle top_k spinbox change."""
        self.top_k_changed.emit(value)

    def get_temperature(self) -> float:
        """Get current temperature value.

        Returns:
            Temperature (0.0-2.0)
        """
        if self._temp_slider:
            return self._temp_slider.value() / 100.0
        return self._temp_default

    def set_temperature(self, value: float) -> None:
        """Set temperature value.

        Args:
            value: Temperature (0.0-2.0)
        """
        if self._temp_slider:
            self._temp_slider.setValue(int(value * 100))

    def get_top_p(self) -> float:
        """Get current top_p value.

        Returns:
            Top P (0.0-1.0)
        """
        if self._p_slider:
            return self._p_slider.value() / 100.0
        return self._p_default

    def set_top_p(self, value: float) -> None:
        """Set top_p value.

        Args:
            value: Top P (0.0-1.0)
        """
        if self._p_slider:
            self._p_slider.setValue(int(value * 100))

    def get_top_k(self) -> int:
        """Get current top_k value.

        Returns:
            Top K (1-100)
        """
        if self._k_spinbox:
            return self._k_spinbox.value()
        return self._k_default

    def set_top_k(self, value: int) -> None:
        """Set top_k value.

        Args:
            value: Top K (1-100)
        """
        if self._k_spinbox:
            self._k_spinbox.setValue(value)

    def to_dict(self) -> dict:
        """Export component state to dictionary.

        Returns:
            State dictionary
        """
        return {
            "temperature": self.get_temperature(),
            "top_p": self.get_top_p(),
            "top_k": self.get_top_k(),
        }

    def from_dict(self, state: dict) -> None:
        """Load component state from dictionary.

        Args:
            state: State dictionary
        """
        if "temperature" in state:
            self.set_temperature(state["temperature"])
        if "top_p" in state:
            self.set_top_p(state["top_p"])
        if "top_k" in state:
            self.set_top_k(state["top_k"])
