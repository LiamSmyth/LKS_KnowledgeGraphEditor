"""Qt Timestamp Configuration Component.

Provides UI for configuring timestamp generation for frame, animation, and clip extraction.
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


from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

# Import from the original module - these dataclasses are shared between tk and Qt
try:
    from scripts.video_extractor.video_extractor import TimestampConfig, TimestampMode
except ImportError:
    # Fallback for when running tests in lks_utils - create minimal mock classes
    from enum import Enum
    from dataclasses import dataclass

    class TimestampMode(str, Enum):
        """Mode for generating extraction timestamps."""

        EVEN_INTERVAL = "even_interval"
        TARGET_COUNT = "target_count"
        SHOT_DETECTION = "shot_detection"
        FULL_VIDEO = "full_video"

    @dataclass
    class TimestampConfig:
        """Configuration for timestamp generation."""

        mode: TimestampMode = TimestampMode.EVEN_INTERVAL
        interval_seconds: float = 5.0
        target_count: int = 20
        shot_threshold: float = 0.3
        min_shot_duration: float = 0.5
        duration_seconds: float = 0.0
        start_offset: float = 0.0
        end_offset: float = 0.0


class QTimestampConfigComponent(QGroupBox):
    """A component for configuring timestamp generation.

    Features:
    - Mode selection (interval, count, shot detection, full video)
    - Mode-specific parameters
    - Duration setting for animations/clips
    - Start/end offset trimming

    Signals:
        config_changed: Emitted when configuration changes.

    Interface:
        get_config() -> TimestampConfig
        set_config(config: TimestampConfig) -> None
        to_dict() -> dict[str, Any]
        from_dict(data: dict[str, Any]) -> None
        set_enabled(enabled: bool) -> None
    """

    config_changed = Signal(object)  # TimestampConfig

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "Timestamp Configuration",
        show_duration: bool = False,
        on_change: Callable[[object], None] | None = None,
    ):
        """Initialize the timestamp config component.

        Args:
            parent: Parent widget.
            title: Component title.
            show_duration: Show duration field (for animations/clips).
            on_change: Optional callback when config changes (legacy support).
        """
        super().__init__(title, parent)

        self.show_duration: bool = show_duration
        self._on_change_callback: Callable[[object], None] | None = on_change
        self._loading: bool = True  # Prevent signals during initialization

        self._create_widgets()
        self._connect_signals()

        self._loading = False

    def _create_widgets(self) -> None:
        """Create the component widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Mode selection
        mode_frame = QFrame()
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(0, 0, 0, 0)

        QLabel("Mode:", mode_frame).setParent(mode_frame)
        mode_layout.addWidget(QLabel("Mode:"))

        self.mode_group = QButtonGroup(self)

        # Radio buttons for modes
        self.interval_radio = QRadioButton("Even Interval")
        self.interval_radio.setToolTip("Extract every N seconds.")
        self.interval_radio.setChecked(True)
        self.mode_group.addButton(
            self.interval_radio, id=0
        )  # Use ID to identify mode
        mode_layout.addWidget(self.interval_radio)

        self.count_radio = QRadioButton("Target Count")
        self.count_radio.setToolTip("Extract N evenly distributed samples.")
        self.mode_group.addButton(self.count_radio, id=1)
        mode_layout.addWidget(self.count_radio)

        self.shot_radio = QRadioButton("Shot Detection")
        self.shot_radio.setToolTip("Extract at scene changes.")
        self.mode_group.addButton(self.shot_radio, id=2)
        mode_layout.addWidget(self.shot_radio)

        # Full Video mode only for animations/clips
        if self.show_duration:
            self.full_video_radio = QRadioButton("Full Video")
            self.full_video_radio.setToolTip(
                "Create a single animation from the entire video (skips if >60s)."
            )
            self.mode_group.addButton(self.full_video_radio, id=3)
            mode_layout.addWidget(self.full_video_radio)
        else:
            self.full_video_radio = None

        mode_layout.addStretch()
        layout.addWidget(mode_frame)

        # Mode-specific settings container
        self.settings_container = QFrame()
        settings_layout = QVBoxLayout(self.settings_container)
        settings_layout.setContentsMargins(0, 0, 0, 0)

        # Interval mode settings
        self.interval_frame = QFrame()
        interval_layout = QHBoxLayout(self.interval_frame)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.addWidget(QLabel("Interval (seconds):"))

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.5, 300.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(5.0)
        self.interval_spin.setToolTip("Seconds between extractions.")
        self.interval_spin.setFixedWidth(100)
        interval_layout.addWidget(self.interval_spin)
        interval_layout.addStretch()

        # Count mode settings
        self.count_frame = QFrame()
        count_layout = QHBoxLayout(self.count_frame)
        count_layout.setContentsMargins(0, 0, 0, 0)
        count_layout.addWidget(QLabel("Number of samples:"))

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 1000)
        self.count_spin.setSingleStep(1)
        self.count_spin.setValue(20)
        self.count_spin.setToolTip(
            "Total number of samples to extract across the video."
        )
        self.count_spin.setFixedWidth(100)
        count_layout.addWidget(self.count_spin)
        count_layout.addStretch()

        # Shot detection settings
        self.shot_frame = QFrame()
        shot_layout = QHBoxLayout(self.shot_frame)
        shot_layout.setContentsMargins(0, 0, 0, 0)

        shot_layout.addWidget(QLabel("Sensitivity:"))
        self.shot_threshold_spin = QDoubleSpinBox()
        self.shot_threshold_spin.setRange(0.1, 1.0)
        self.shot_threshold_spin.setSingleStep(0.1)
        self.shot_threshold_spin.setValue(0.3)
        self.shot_threshold_spin.setDecimals(1)
        self.shot_threshold_spin.setToolTip(
            "Shot detection sensitivity (0.0-1.0).\nLower = more sensitive (more shots detected)."
        )
        self.shot_threshold_spin.setFixedWidth(80)
        shot_layout.addWidget(self.shot_threshold_spin)

        shot_layout.addSpacing(20)
        shot_layout.addWidget(QLabel("Min gap (s):"))
        self.min_shot_duration_spin = QDoubleSpinBox()
        self.min_shot_duration_spin.setRange(0.1, 10.0)
        self.min_shot_duration_spin.setSingleStep(0.1)
        self.min_shot_duration_spin.setValue(0.5)
        self.min_shot_duration_spin.setToolTip(
            "Minimum duration between detected shots in seconds."
        )
        self.min_shot_duration_spin.setFixedWidth(80)
        shot_layout.addWidget(self.min_shot_duration_spin)
        shot_layout.addStretch()

        # Add mode frames to settings container (will show/hide based on mode)
        settings_layout.addWidget(self.interval_frame)
        settings_layout.addWidget(self.count_frame)
        settings_layout.addWidget(self.shot_frame)

        layout.addWidget(self.settings_container)

        # Duration (for animations/clips)
        if self.show_duration:
            duration_frame = QFrame()
            duration_layout = QHBoxLayout(duration_frame)
            duration_layout.setContentsMargins(0, 0, 0, 0)

            duration_layout.addWidget(QLabel("Duration (seconds):"))
            self.duration_spin = QDoubleSpinBox()
            self.duration_spin.setRange(0.5, 60.0)
            self.duration_spin.setSingleStep(0.5)
            self.duration_spin.setValue(2.0)
            self.duration_spin.setToolTip(
                "Duration of each extracted clip/animation in seconds."
            )
            self.duration_spin.setFixedWidth(100)
            duration_layout.addWidget(self.duration_spin)

            label = QLabel("(per animation/clip)")
            label.setStyleSheet("color: #6c757d;")  # secondary color
            duration_layout.addWidget(label)
            duration_layout.addStretch()

            layout.addWidget(duration_frame)
        else:
            self.duration_spin = None

        # Offsets
        offset_frame = QFrame()
        offset_layout = QHBoxLayout(offset_frame)
        offset_layout.setContentsMargins(0, 0, 0, 0)

        offset_layout.addWidget(QLabel("Skip from start (s):"))
        self.start_offset_spin = QDoubleSpinBox()
        self.start_offset_spin.setRange(0, 300.0)
        self.start_offset_spin.setSingleStep(1.0)
        self.start_offset_spin.setValue(0.0)
        self.start_offset_spin.setToolTip(
            "Ignore this many seconds from the beginning of the video."
        )
        self.start_offset_spin.setFixedWidth(100)
        offset_layout.addWidget(self.start_offset_spin)

        offset_layout.addSpacing(20)
        offset_layout.addWidget(QLabel("Skip from end (s):"))
        self.end_offset_spin = QDoubleSpinBox()
        self.end_offset_spin.setRange(0, 300.0)
        self.end_offset_spin.setSingleStep(1.0)
        self.end_offset_spin.setValue(0.0)
        self.end_offset_spin.setToolTip(
            "Ignore this many seconds from the end of the video."
        )
        self.end_offset_spin.setFixedWidth(100)
        offset_layout.addWidget(self.end_offset_spin)
        offset_layout.addStretch()

        layout.addWidget(offset_frame)

        # Initialize mode display
        self._update_mode_display()

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.mode_group.buttonClicked.connect(self._on_mode_changed)
        self.interval_spin.valueChanged.connect(self._emit_config_changed)
        self.count_spin.valueChanged.connect(self._emit_config_changed)
        self.shot_threshold_spin.valueChanged.connect(
            self._emit_config_changed)
        self.min_shot_duration_spin.valueChanged.connect(
            self._emit_config_changed)
        self.start_offset_spin.valueChanged.connect(self._emit_config_changed)
        self.end_offset_spin.valueChanged.connect(self._emit_config_changed)
        if self.duration_spin:
            self.duration_spin.valueChanged.connect(self._emit_config_changed)

    def _on_mode_changed(self) -> None:
        """Handle mode selection change."""
        self._update_mode_display()
        self._emit_config_changed()

    def _update_mode_display(self) -> None:
        """Update visibility of mode-specific widgets."""
        checked_id = self.mode_group.checkedId()

        # Hide all
        self.interval_frame.hide()
        self.count_frame.hide()
        self.shot_frame.hide()

        # Show the relevant one
        if checked_id == 0:  # Even Interval
            self.interval_frame.show()
        elif checked_id == 1:  # Target Count
            self.count_frame.show()
        elif checked_id == 2:  # Shot Detection
            self.shot_frame.show()
        # else: Full Video (no settings to show)

        # Disable duration spin for Full Video mode
        if self.duration_spin:
            if checked_id == 3:  # Full Video
                self.duration_spin.setEnabled(False)
            else:
                self.duration_spin.setEnabled(True)

    def _emit_config_changed(self) -> None:
        """Emit config changed signal."""
        if self._loading:
            return

        config = self.get_config()
        self.config_changed.emit(config)

        # Call legacy callback if provided
        if self._on_change_callback:
            self._on_change_callback(config)

    def get_config(self) -> object:
        """Get the current timestamp configuration.

        Returns:
            TimestampConfig instance.
        """
        # Determine mode from radio button
        checked_id = self.mode_group.checkedId()
        if checked_id == 0:
            mode = TimestampMode.EVEN_INTERVAL
        elif checked_id == 1:
            mode = TimestampMode.TARGET_COUNT
        elif checked_id == 2:
            mode = TimestampMode.SHOT_DETECTION
        elif checked_id == 3:
            mode = TimestampMode.FULL_VIDEO
        else:
            mode = TimestampMode.EVEN_INTERVAL  # fallback

        return TimestampConfig(
            mode=mode,
            interval_seconds=self.interval_spin.value(),
            target_count=self.count_spin.value(),
            shot_threshold=self.shot_threshold_spin.value(),
            min_shot_duration=self.min_shot_duration_spin.value(),
            duration_seconds=self.duration_spin.value()
            if self.duration_spin
            else 0.0,
            start_offset=self.start_offset_spin.value(),
            end_offset=self.end_offset_spin.value(),
        )

    def set_config(self, config: object) -> None:
        """Set the timestamp configuration.

        Args:
            config: TimestampConfig instance.
        """
        self._loading = True

        # Set mode
        if config.mode == TimestampMode.EVEN_INTERVAL:
            self.interval_radio.setChecked(True)
        elif config.mode == TimestampMode.TARGET_COUNT:
            self.count_radio.setChecked(True)
        elif config.mode == TimestampMode.SHOT_DETECTION:
            self.shot_radio.setChecked(True)
        elif config.mode == TimestampMode.FULL_VIDEO and self.full_video_radio:
            self.full_video_radio.setChecked(True)

        # Set values
        self.interval_spin.setValue(config.interval_seconds)
        self.count_spin.setValue(config.target_count)
        self.shot_threshold_spin.setValue(config.shot_threshold)
        self.min_shot_duration_spin.setValue(config.min_shot_duration)
        if self.duration_spin:
            self.duration_spin.setValue(config.duration_seconds)
        self.start_offset_spin.setValue(config.start_offset)
        self.end_offset_spin.setValue(config.end_offset)

        self._update_mode_display()
        self._loading = False

    def to_dict(self) -> dict[str, any]:
        """Export configuration to dictionary.

        Returns:
            Dictionary containing all configuration values.
        """
        checked_id = self.mode_group.checkedId()
        mode_map = {
            0: "even_interval",
            1: "target_count",
            2: "shot_detection",
            3: "full_video",
        }

        return {
            "mode": mode_map.get(checked_id, "even_interval"),
            "interval_seconds": self.interval_spin.value(),
            "target_count": self.count_spin.value(),
            "shot_threshold": self.shot_threshold_spin.value(),
            "min_shot_duration": self.min_shot_duration_spin.value(),
            "duration_seconds": self.duration_spin.value()
            if self.duration_spin
            else 0.0,
            "start_offset": self.start_offset_spin.value(),
            "end_offset": self.end_offset_spin.value(),
        }

    def from_dict(self, data: dict[str, any]) -> None:
        """Load configuration from dictionary.

        Args:
            data: Dictionary with configuration values.
        """
        self._loading = True

        # Set mode
        mode = data.get("mode", "even_interval")
        if mode == "even_interval":
            self.interval_radio.setChecked(True)
        elif mode == "target_count":
            self.count_radio.setChecked(True)
        elif mode == "shot_detection":
            self.shot_radio.setChecked(True)
        elif mode == "full_video" and self.full_video_radio:
            self.full_video_radio.setChecked(True)

        # Set values
        self.interval_spin.setValue(data.get("interval_seconds", 5.0))
        self.count_spin.setValue(data.get("target_count", 20))
        self.shot_threshold_spin.setValue(data.get("shot_threshold", 0.3))
        self.min_shot_duration_spin.setValue(
            data.get("min_shot_duration", 0.5))
        if self.duration_spin:
            self.duration_spin.setValue(data.get("duration_seconds", 2.0))
        self.start_offset_spin.setValue(data.get("start_offset", 0.0))
        self.end_offset_spin.setValue(data.get("end_offset", 0.0))

        self._update_mode_display()
        self._loading = False

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the component.

        Args:
            enabled: Whether to enable the component.
        """
        self.setEnabled(enabled)
