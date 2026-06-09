"""``QFrameProfilerWidget`` with split preview/details profiling workflow.

The widget separates:

* **Profile Preview** (fast, live): high-frequency graph + KPI strip.
* **Profile Details** (inspect): populated only when capture is paused or
  the user scrubs/selects a frame.

This avoids expensive details-table rebuilding on every frame while still
keeping a responsive live preview.
"""
from __future__ import annotations

from dataclasses import replace
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from lks_utils.profiling.adapters.canvas_frame_timings_adapter import CanvasFrameTimingsAdapter
from lks_utils.profiling import (
    FrameCaptureController,
    FrameProfileDetailsBuilder,
    get_default_action_timing_profiler,
)
from lks_utils.profiling.counter_track import CounterTrack
from lks_utils.profiling.device import Device
from lks_utils.profiling.profile_filter import ProfileFilter
from lks_utils.profiling.ui import (
    QProfileActionsWidget,
    QProfileCountersWidget,
    QProfileHierarchyWidget,
    QProfilePreviewGraphWidget,
    QProfileTimelineWidget,
)
from lks_utils.profiling.ui.perf_gradient_mapper import PerfGradientMapper

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.render.canvas_renderer import FrameTimings

_RING_SIZE: int = 240
_DEFAULT_BUDGET_MS: float = 16.6
_LIVE_REFRESH_INTERVAL_MS: int = 16
_FROZEN_REFRESH_INTERVAL_MS: int = 125
_COLOR_TEXT = QColor(0xCC, 0xCC, 0xCC)
# orange tint for untracked rows
_COLOR_RESIDUAL_WARN = QColor(0xFF, 0x80, 0x00)


class QFrameProfilerWidget(QWidget):
    """Frame profiler widget with split preview/details behavior.

    Signals:
        profiler_warning(str): Emitted when a frame's unaccounted time
            exceeds the warn threshold.  The payload is a human-readable
            message suitable for logging or LLM review.
    """

    profiler_warning = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._budget_ms: float = _DEFAULT_BUDGET_MS
        self._profile_filter: ProfileFilter = ProfileFilter()
        self._capture = FrameCaptureController(max_frames=_RING_SIZE)
        self._gradient = PerfGradientMapper(self._budget_ms)
        self._action_profiler = get_default_action_timing_profiler()
        self._attached_filter: _PaintEventFilter | None = None
        self._attached_canvas: QWidget | None = None
        self._processing_enabled: bool = True
        self._last_preview_revision: int = -1
        self._last_action_revision: int = -1
        self._last_details_token: tuple[int, int, float] | None = None

        # Built-in counter tracks populated automatically by push()
        self._draw_calls_track = CounterTrack(
            "draw_calls", max_samples=_RING_SIZE)
        self._overlay_ms_track = CounterTrack(
            "overlay_ms", max_samples=_RING_SIZE)

        self._build_ui()
        # Register built-in tracks in the Counters tab after UI is built
        self._counters_widget.set_tracks(
            [self._draw_calls_track, self._overlay_ms_track]
        )
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(_LIVE_REFRESH_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start()

    def push(self, timings: FrameTimings | None) -> None:
        """Feed one frame timing sample (ignored while capture paused)."""
        if not self._processing_enabled:
            return
        self._capture.push(timings)
        if timings is not None:
            self._draw_calls_track.push(float(len(timings.overlay_timings)))
            self._overlay_ms_track.push(float(timings.overlays_ms))
            if self._details_tabs.currentIndex() == 3:  # Counters tab visible
                self._counters_widget.refresh()

    def set_processing_enabled(self, enabled: bool) -> None:
        """Enable/disable all live profiler work for the attached canvas."""
        enabled = bool(enabled)
        if self._processing_enabled == enabled:
            return
        self._processing_enabled = enabled
        if not self._processing_enabled:
            self._refresh_timer.stop()
            self._apply_gpu_timer_mode(False)
            return
        self._apply_gpu_timer_mode(self._gpu_timers_cb.isChecked())
        self._sync_refresh_interval()
        self._refresh(force_details=True)

    def set_counter_tracks(self, tracks: list) -> None:
        """Set the counter tracks shown in the Counters tab.

        Each track should be a :class:`~lks_utils.profiling.CounterTrack`
        instance.  Call :meth:`~lks_utils.profiling.ui.QProfileCountersWidget.refresh`
        after pushing new samples to repaint the mini-graphs.

        Example::

            draw_calls = CounterTrack("draw_calls")
            profiler_widget.set_counter_tracks([draw_calls])
            # each frame:
            draw_calls.push(n_draws)
            profiler_widget.refresh_counters()
        """
        self._counters_widget.set_tracks(tracks)

    def refresh_counters(self) -> None:
        """Repaint counter mini-graphs (call after pushing new counter samples)."""
        self._counters_widget.refresh()

    def set_capture_enabled(self, enabled: bool) -> None:
        if enabled and not self._processing_enabled:
            self._processing_enabled = True
        self._capture.set_capture_enabled(enabled)
        if enabled:
            self._capture.select_live()
        block = self._capture_cb.blockSignals(True)
        self._capture_cb.setChecked(enabled)
        self._capture_cb.blockSignals(block)
        if enabled:
            self._apply_gpu_timer_mode(self._gpu_timers_cb.isChecked())
        self._sync_refresh_interval()
        self._refresh(force_details=True)

    @property
    def capture_enabled(self) -> bool:
        return self._capture.capture_enabled

    def attach(self, canvas: QWidget) -> None:
        """Wire *canvas* paint events to auto-push frame timings."""
        if self._attached_filter is not None:
            self._apply_gpu_timer_mode(False)
            self._detach_canvas_sources()
        self._attached_filter = _PaintEventFilter(canvas, self)
        canvas.installEventFilter(self._attached_filter)
        signal = getattr(canvas, "frame_timings_ready", None)
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(self.push)
        self._attached_canvas = canvas
        self._apply_gpu_timer_mode(self._gpu_timers_cb.isChecked())

    def detach(self) -> None:
        if self._attached_filter is not None:
            self._apply_gpu_timer_mode(False)
            self._detach_canvas_sources()
            self._attached_filter = None
            self._attached_canvas = None

    def _detach_canvas_sources(self) -> None:
        if self._attached_canvas is not None:
            signal = getattr(self._attached_canvas,
                             "frame_timings_ready", None)
            if signal is not None and hasattr(signal, "disconnect"):
                try:
                    signal.disconnect(self.push)
                except (RuntimeError, TypeError):
                    pass
        if self._attached_filter is not None:
            self._attached_filter.setParent(None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        # ── Toolbar ────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._capture_cb = QCheckBox("Capture")
        self._capture_cb.setChecked(True)
        self._capture_cb.toggled.connect(self._on_capture_toggled)

        self._gpu_timers_cb = QCheckBox("GPU timers")
        self._gpu_timers_cb.setChecked(False)
        self._gpu_timers_cb.setToolTip(
            "Enable timer-query profiling for GPU overlay passes (diagnostic mode; adds overhead)."
        )
        self._gpu_timers_cb.toggled.connect(self._on_gpu_timers_toggled)

        self._focus_live_btn = QPushButton("Focus Live")
        self._focus_live_btn.setMaximumWidth(92)
        self._focus_live_btn.clicked.connect(self._on_focus_live)

        self._status_badge = QLabel("IDLE")
        self._status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_badge.setMinimumWidth(56)
        self._status_badge.setFont(QFont("Consolas", 8))

        self._kpi_label = QLabel(
            "preview total -- ms | fps --.- | budget --.- ms")
        self._kpi_label.setFont(QFont("Consolas", 9))

        clear_btn = QPushButton("Clear")
        clear_btn.setMaximumWidth(58)
        clear_btn.clicked.connect(self._on_clear)

        copy_btn = QPushButton("Copy Profile")
        copy_btn.setMaximumWidth(96)
        copy_btn.setToolTip(
            "Copy the current frame profile report to clipboard (paste into LLM for review)")
        copy_btn.clicked.connect(self._on_copy_profile)

        self._save_session_btn = QPushButton("Save Session")
        self._save_session_btn.setMaximumWidth(100)
        self._save_session_btn.setToolTip(
            "Export all buffered frames to a .lksprof session file")
        self._save_session_btn.clicked.connect(self._on_save_session)

        self._load_session_btn = QPushButton("Load Session")
        self._load_session_btn.setMaximumWidth(100)
        self._load_session_btn.setToolTip(
            "Load a .lksprof session file for offline inspection (enters Replay mode)")
        self._load_session_btn.clicked.connect(self._on_load_session)

        # FPS / ms target spinboxes ─────────────────────────────────────────
        fps_label = QLabel("target:")
        fps_label.setFont(QFont("Consolas", 8))
        fps_label.setStyleSheet("color: #b9b9b9;")

        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 500.0)
        self._fps_spin.setDecimals(1)
        self._fps_spin.setSuffix(" fps")
        self._fps_spin.setValue(1000.0 / max(self._budget_ms, 1e-6))
        self._fps_spin.setFixedWidth(80)
        self._fps_spin.setToolTip(
            "Target frame rate — updates the ms budget field automatically")
        self._fps_spin.editingFinished.connect(self._on_fps_confirmed)

        self._ms_spin = QDoubleSpinBox()
        self._ms_spin.setRange(0.1, 1000.0)
        self._ms_spin.setDecimals(2)
        self._ms_spin.setSuffix(" ms")
        self._ms_spin.setValue(self._budget_ms)
        self._ms_spin.setFixedWidth(80)
        self._ms_spin.setToolTip(
            "Target frame time in milliseconds — updates the fps field automatically")
        self._ms_spin.editingFinished.connect(self._on_ms_confirmed)

        toolbar.addWidget(self._capture_cb)
        toolbar.addWidget(self._gpu_timers_cb)
        toolbar.addWidget(self._focus_live_btn)
        toolbar.addWidget(self._status_badge)
        toolbar.addWidget(self._kpi_label)
        toolbar.addStretch()
        toolbar.addWidget(fps_label)
        toolbar.addWidget(self._fps_spin)
        toolbar.addWidget(self._ms_spin)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(copy_btn)
        toolbar.addWidget(self._save_session_btn)
        toolbar.addWidget(self._load_session_btn)
        layout.addLayout(toolbar)

        # ── Second toolbar row: navigation + filter controls (Phase D) ─────
        nav_filter_row = QHBoxLayout()
        nav_filter_row.setSpacing(6)

        self._prev_btn = QPushButton("◀")
        self._prev_btn.setMaximumWidth(32)
        self._prev_btn.setToolTip("Previous frame  (left-arrow)")
        self._prev_btn.clicked.connect(self._on_prev_frame)

        self._next_btn = QPushButton("▶")
        self._next_btn.setMaximumWidth(32)
        self._next_btn.setToolTip("Next frame  (right-arrow)")
        self._next_btn.clicked.connect(self._on_next_frame)

        self._frame_label = QPushButton("frame --/--  |  age -- ms")
        self._frame_label.setFont(QFont("Consolas", 8))
        self._frame_label.setFlat(True)
        self._frame_label.setToolTip("Click to jump to a specific frame index")
        self._frame_label.setStyleSheet(
            "QPushButton { color: #b9b9b9; text-align: left; padding: 0 4px; border: none; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        self._frame_label.clicked.connect(self._on_frame_label_clicked)

        search_label = QLabel("🔍")
        search_label.setFont(QFont("Segoe UI", 9))
        search_label.setToolTip("Filter nodes by name (substring match)")

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("filter nodes…")
        self._search_edit.setMaximumWidth(160)
        self._search_edit.setFont(QFont("Consolas", 9))
        self._search_edit.setToolTip(
            "Case-insensitive substring filter applied to all detail views")
        self._search_edit.textChanged.connect(self._on_filter_changed)

        self._device_combo = QComboBox()
        self._device_combo.addItems(["All", "CPU", "GPU"])
        self._device_combo.setMaximumWidth(68)
        self._device_combo.setFont(QFont("Consolas", 9))
        self._device_combo.setToolTip("Filter nodes by device type")
        self._device_combo.currentTextChanged.connect(self._on_filter_changed)

        nav_filter_row.addWidget(self._prev_btn)
        nav_filter_row.addWidget(self._next_btn)
        nav_filter_row.addWidget(self._frame_label, 1)
        nav_filter_row.addStretch()
        nav_filter_row.addWidget(search_label)
        nav_filter_row.addWidget(self._search_edit)
        nav_filter_row.addWidget(self._device_combo)
        layout.addLayout(nav_filter_row)

        # ── Splitter (preview top / details bottom) ────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet(
            "QSplitter::handle { background-color: #383838; border-radius: 2px; }")

        self._preview_graph = QProfilePreviewGraphWidget(self)
        self._preview_graph.set_budget_ms(self._budget_ms)
        self._preview_graph.frame_selected.connect(
            self._on_preview_frame_selected)
        self._preview_graph.frame_scrubbed.connect(
            self._on_preview_frame_scrubbed)
        splitter.addWidget(self._preview_graph)

        details_container = QWidget()
        details_layout = QVBoxLayout(details_container)
        details_layout.setContentsMargins(0, 2, 0, 0)
        details_layout.setSpacing(3)

        self._details_hint = QLabel(
            "Profile Details: pause capture to inspect selected frame")
        self._details_hint.setFont(QFont("Consolas", 8))
        self._details_hint.setStyleSheet("color: #aaaaaa;")
        details_layout.addWidget(self._details_hint)

        self._details_tabs = QTabWidget(details_container)
        self._details_tabs.setDocumentMode(True)
        details_layout.addWidget(self._details_tabs, 1)

        flat_tab = QWidget(self._details_tabs)
        flat_layout = QVBoxLayout(flat_tab)
        flat_layout.setContentsMargins(0, 0, 0, 0)
        flat_layout.setSpacing(0)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Stage", "Kind", "Z", "ms", "%"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setFont(QFont("Consolas", 9))
        self._table.setMinimumHeight(80)
        flat_layout.addWidget(self._table)

        self._hierarchy_widget = QProfileHierarchyWidget(self._details_tabs)
        self._hierarchy_widget.set_budget_ms(self._budget_ms)

        self._timeline_widget = QProfileTimelineWidget(self._details_tabs)
        self._timeline_widget.set_budget_ms(self._budget_ms)
        self._timeline_widget.block_selected.connect(
            self._on_timeline_block_selected)

        self._counters_widget = QProfileCountersWidget(self._details_tabs)
        # Frame cursor linkage: sync hover cursor in counters to selected frame
        self._preview_graph.frame_selected.connect(
            self._counters_widget.set_hover_index)
        self._preview_graph.frame_scrubbed.connect(
            self._counters_widget.set_hover_index)

        self._details_tabs.addTab(flat_tab, "Flat")
        self._details_tabs.addTab(self._hierarchy_widget, "Hierarchy")
        self._details_tabs.addTab(self._timeline_widget, "Timeline")
        self._details_tabs.addTab(self._counters_widget, "Counters")
        self._actions_widget = QProfileActionsWidget(self._details_tabs)
        self._details_tabs.addTab(self._actions_widget, "Actions")

        splitter.addWidget(details_container)
        splitter.setSizes([160, 200])
        layout.addWidget(splitter, 1)

    def _on_capture_toggled(self, checked: bool) -> None:
        self.set_capture_enabled(bool(checked))

    def _on_gpu_timers_toggled(self, checked: bool) -> None:
        self._apply_gpu_timer_mode(bool(checked))

    def _apply_gpu_timer_mode(self, enabled: bool) -> None:
        if self._attached_canvas is None:
            return
        setter = getattr(self._attached_canvas,
                         "set_gpu_timer_profiling_enabled", None)
        if callable(setter):
            setter(enabled)

    def _on_focus_live(self) -> None:
        self.set_capture_enabled(True)

    def _sync_refresh_interval(self) -> None:
        if not self._processing_enabled:
            if self._refresh_timer.isActive():
                self._refresh_timer.stop()
            return
        interval = (
            _LIVE_REFRESH_INTERVAL_MS
            if self._capture.capture_enabled or self._capture.replay_mode
            else _FROZEN_REFRESH_INTERVAL_MS
        )
        if self._refresh_timer.interval() != interval:
            self._refresh_timer.setInterval(interval)
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def _on_clear(self) -> None:
        self._capture.clear()
        self._action_profiler.clear()
        self._last_action_revision = -1
        self._actions_widget.clear()
        self._last_details_token = None
        self._refresh(force_details=True)

    def _on_copy_profile(self) -> None:
        report = self._format_copy_profile_report()
        QApplication.clipboard().setText(report)

    def _format_copy_profile_report(self) -> str:
        frame_report = self.format_profile_report()
        actions_report = self._format_action_report()
        sections: list[str] = []
        if frame_report:
            sections.append(frame_report)
        if actions_report:
            sections.append(actions_report)
        return "\n\n".join(sections)

    def _format_action_report(self, *, max_stats: int = 16, max_events: int = 40) -> str:
        stats = self._action_profiler.stats()
        events = self._action_profiler.events()
        lines: list[str] = ["Action Timing Summary"]
        lines.append(
            f"events={len(events)} | unique_actions={len(stats)}"
        )
        if not stats:
            lines.append("No action timing samples recorded.")
            return "\n".join(lines)

        lines.append("Top Actions (sorted by p95):")
        for row in stats[: max(1, int(max_stats))]:
            lines.append(
                f"- {row.action_id}:{row.phase} count={row.count} "
                f"p50={row.p50_ms:.3f}ms p95={row.p95_ms:.3f}ms "
                f"p99={row.p99_ms:.3f}ms mean={row.mean_ms:.3f}ms "
                f"max={row.max_ms:.3f}ms outcomes={self._format_action_outcomes(row.outcomes)}"
            )

        if events:
            lines.append("Recent Events:")
            recent = list(reversed(events[-max(1, int(max_events)):]))
            for event in recent:
                lines.append(
                    f"- {event.action_id}:{event.phase} "
                    f"duration={event.duration_ms:.3f}ms outcome={event.outcome} "
                    f"metadata={self._format_action_metadata(event.metadata)}"
                )

        return "\n".join(lines)

    @staticmethod
    def _format_action_metadata(metadata: dict[str, object]) -> str:
        if not metadata:
            return "{}"
        parts: list[str] = []
        for key in sorted(metadata):
            parts.append(f"{key}={metadata[key]}")
        return "{" + ", ".join(parts) + "}"

    @staticmethod
    def _format_action_outcomes(outcomes: dict[str, int]) -> str:
        if not outcomes:
            return "{}"
        keys = sorted(outcomes)
        return "{" + ", ".join(f"{key}:{outcomes[key]}" for key in keys) + "}"

    def _on_save_session(self) -> None:
        """Export buffered frames to a .lksprof gzip JSONL session file."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Profiling Session",
            "",
            "Profiler Session (*.lksprof);;All Files (*)",
        )
        if not path:
            return
        try:
            count = self._capture.export_session(
                path,
                lambda f, idx: CanvasFrameTimingsAdapter.adapt(
                    f, frame_index=idx),
            )
            self._details_hint.setText(
                f"Session saved: {count} frame(s) → {path}"
            )
        except Exception as exc:  # noqa: BLE001
            self._details_hint.setText(f"Save failed: {exc}")

    def _on_load_session(self) -> None:
        """Load a .lksprof session file and enter replay mode."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Profiling Session",
            "",
            "Profiler Session (*.lksprof);;All Files (*)",
        )
        if not path:
            return
        try:
            count = self._capture.load_session(path)
            self._capture_cb.setChecked(False)
            self._details_hint.setText(
                f"Replay mode: {count} frame(s) loaded from {path}"
            )
            self._last_details_token = None
            self._refresh(force_details=True)
        except Exception as exc:  # noqa: BLE001
            self._details_hint.setText(f"Load failed: {exc}")

    def _on_fps_confirmed(self) -> None:
        fps = self._fps_spin.value()
        ms = 1000.0 / max(fps, 1e-6)
        self._apply_budget_ms(ms)
        block = self._ms_spin.blockSignals(True)
        self._ms_spin.setValue(ms)
        self._ms_spin.blockSignals(block)

    def _on_ms_confirmed(self) -> None:
        ms = self._ms_spin.value()
        fps = 1000.0 / max(ms, 1e-6)
        self._apply_budget_ms(ms)
        block = self._fps_spin.blockSignals(True)
        self._fps_spin.setValue(fps)
        self._fps_spin.blockSignals(block)

    def format_profile_report(self, frame: FrameTimings | None = None) -> str:
        """Return a plain-text profile report for the given (or selected) frame.

        The report is formatted for easy LLM paste-back review.  A
        ``WARNING`` prefix is prepended automatically when unaccounted time
        exceeds the warn threshold.

        Returns an empty string if no frame is available.
        """
        frame_total_ms: float | None = None
        if frame is None:
            frames = self._capture.frames()
            state = self._capture.state()
            if not frames or state.selected_index < 0:
                return ""
            frame_total_ms = self._effective_frame_total_ms(
                frames,
                state.selected_index,
            )
            cadence_wait_ms = self._cadence_wait_ms(
                frames,
                state.selected_index,
            )
            frame = frames[state.selected_index]
        else:
            cadence_wait_ms = None
        return FrameProfileDetailsBuilder.format_report(
            frame,
            budget_ms=self._budget_ms,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )

    def get_perf_report_dict(self, frame: FrameTimings | None = None) -> dict[str, object]:
        """Return structured profiling data for programmatic / test inspection.

        Suitable for automated assertions in pytest live-query tests::

            report = widget.get_perf_report_dict()
            assert report["residual_pct"] < 15.0, "Too much untracked time"
        """
        frame_total_ms: float | None = None
        if frame is None:
            frames = self._capture.frames()
            state = self._capture.state()
            if not frames or state.selected_index < 0:
                return {}
            frame_total_ms = self._effective_frame_total_ms(
                frames,
                state.selected_index,
            )
            cadence_wait_ms = self._cadence_wait_ms(
                frames,
                state.selected_index,
            )
            frame = frames[state.selected_index]
        else:
            cadence_wait_ms = None
        paint_total_ms = float(frame.total_ms)
        total_ms = paint_total_ms if frame_total_ms is None else float(
            frame_total_ms)
        residual = FrameProfileDetailsBuilder.residual_ms(
            frame,
        )
        cadence_gap = FrameProfileDetailsBuilder.cadence_gap_ms(
            frame,
            frame_total_ms=frame_total_ms,
        )
        cadence_wait, cadence_present = FrameProfileDetailsBuilder.cadence_breakdown_ms(
            frame,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )
        residual_pct = FrameProfileDetailsBuilder.residual_fraction(
            frame,
            frame_total_ms=frame_total_ms,
        ) * 100.0
        cadence_gap_pct = (cadence_gap / max(total_ms, 1e-6)) * 100.0
        rows = FrameProfileDetailsBuilder.build_rows(
            frame,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )
        return {
            "effective_total_ms": total_ms,
            "paint_total_ms": paint_total_ms,
            "total_ms": total_ms,
            "budget_ms": self._budget_ms,
            "budget_delta_ms": total_ms - self._budget_ms,
            "background_ms": frame.background_ms,
            "items_ms": frame.items_ms,
            "overlays_ms": frame.overlays_ms,
            "timed_render_ms": frame.background_ms + frame.items_ms + frame.overlays_ms,
            "residual_ms": residual,
            "residual_pct": residual_pct,
            "cadence_gap_ms": cadence_gap,
            "cadence_gap_pct": cadence_gap_pct,
            "cadence_wait_ms": cadence_wait,
            "cadence_present_ms": cadence_present,
            "stages": [
                {"name": name, "kind": kind, "z": z_str, "ms": ms, "pct": pct}
                for name, kind, z_str, ms, pct in rows
            ],
        }

    def _apply_budget_ms(self, budget_ms: float) -> None:
        self._budget_ms = max(0.1, float(budget_ms))
        self._gradient.set_budget_ms(self._budget_ms)
        self._preview_graph.set_budget_ms(self._budget_ms)
        self._hierarchy_widget.set_budget_ms(self._budget_ms)
        self._timeline_widget.set_budget_ms(self._budget_ms)
        self._last_details_token = None
        self._refresh(force_details=True)

    def _on_preview_frame_selected(self, idx: int) -> None:
        self._capture.select_frame(idx)
        block = self._capture_cb.blockSignals(True)
        self._capture_cb.setChecked(False)
        self._capture_cb.blockSignals(block)
        self._refresh(force_details=True)

    def _on_preview_frame_scrubbed(self, idx: int) -> None:
        if self._capture.capture_enabled:
            return
        self._capture.select_frame(idx)
        self._refresh(force_details=True)

    def _refresh(self, *, force_details: bool = False) -> None:
        self._refresh_actions_tab()
        if self._capture.replay_mode:
            self._refresh_replay(force_details=force_details)
            return

        frames = self._capture.frames()
        state = self._capture.state()

        if self._last_preview_revision != self._capture.revision:
            # Use cadence-aware totals for the preview so ribbon/KPIs reflect
            # user-visible frame pacing, not only measured draw work.
            preview_frames = self._with_cadence_aligned_totals(frames)
            self._preview_graph.set_frames(
                preview_frames,
                selected_idx=state.selected_index,
                live_idx=state.live_index,
            )
            self._last_preview_revision = self._capture.revision
        self._preview_graph.set_scrub_enabled(not state.capture_enabled)

        if state.selected_index < 0 or not frames:
            self._status_badge.setText("IDLE")
            self._status_badge.setStyleSheet("")
            self._kpi_label.setText(
                "preview total -- ms | fps --.- | budget --.- ms")
            self._frame_label.setText("frame --/-- | age -- ms")
            self._details_hint.setText(
                "Profile Details: pause capture to inspect selected frame")
            self._table.setRowCount(0)
            self._hierarchy_widget.set_frame_sample(None)
            self._timeline_widget.set_frame_sample(None)
            self._last_details_token = None
            return

        frame = frames[state.selected_index]
        fps = self._fps_from_cadence(frames, state.selected_index)
        frame_total_ms = self._effective_frame_total_ms(
            frames,
            state.selected_index,
        )
        budget_delta = frame_total_ms - self._budget_ms
        age_ms = (time.perf_counter() - frame.frame_timestamp) * 1000.0

        self._kpi_label.setText(
            f"preview total {frame_total_ms:6.2f} ms | fps {fps:5.1f} | budget {budget_delta:+6.2f} ms"
        )
        self._frame_label.setText(
            f"frame {state.selected_index + 1}/{state.frame_count} | age {age_ms:.0f} ms"
        )
        self._update_status_badge(frame_total_ms)

        if state.capture_enabled:
            self._details_hint.setText(
                "Profile Details: capture running (pause/scrub to inspect)")
            if force_details or self._table.rowCount() > 0:
                self._table.setRowCount(0)
            self._hierarchy_widget.set_frame_sample(None)
            self._timeline_widget.set_frame_sample(None)
            self._last_details_token = None
            # Emit warning on live frames even while capture is running.
            self._check_emit_warning(frame, frame_total_ms=frame_total_ms)
            return

        self._details_hint.setText("Profile Details: frozen selection")
        token = (state.selected_index, state.frame_count,
                 frame.frame_timestamp)
        if not force_details and token == self._last_details_token:
            return
        self._last_details_token = token
        self._populate_details(frame, frame_total_ms=frame_total_ms)
        sample = CanvasFrameTimingsAdapter.adapt(
            frame, frame_index=state.selected_index)
        self._hierarchy_widget.set_frame_sample(sample)
        self._timeline_widget.set_frame_sample(sample)
        self._check_emit_warning(frame, frame_total_ms=frame_total_ms)

    def _on_timeline_block_selected(self, node_name: str) -> None:
        self._hierarchy_widget.select_first_by_name(node_name)

    # ── Phase D: navigation and filter handlers ────────────────────────────

    def _on_prev_frame(self) -> None:
        state = self._capture.state()
        if self._capture.replay_mode:
            samples = self._capture.replay_samples()
            idx = max(0, state.selected_index - 1)
            if idx != state.selected_index:
                self._capture.select_frame(idx)
                self._refresh(force_details=True)
            return
        if state.selected_index > 0:
            self._capture.select_frame(state.selected_index - 1)
            self.set_capture_enabled(False)
            self._refresh(force_details=True)

    def _on_next_frame(self) -> None:
        state = self._capture.state()
        if self._capture.replay_mode:
            samples = self._capture.replay_samples()
            idx = min(len(samples) - 1, state.selected_index + 1)
            if idx != state.selected_index:
                self._capture.select_frame(idx)
                self._refresh(force_details=True)
            return
        frames = self._capture.frames()
        if state.selected_index < len(frames) - 1:
            self._capture.select_frame(state.selected_index + 1)
            self.set_capture_enabled(False)
            self._refresh(force_details=True)

    def _on_frame_label_clicked(self) -> None:
        """Open a jump-to-frame dialog and select the requested index."""
        frames = self._capture.frames()
        if not frames:
            return
        state = self._capture.state()
        dlg = QDialog(self)
        dlg.setWindowTitle("Jump to Frame")
        dlg_layout = QVBoxLayout(dlg)
        spin = QSpinBox(dlg)
        spin.setRange(1, len(frames))
        spin.setValue(max(1, state.selected_index + 1))
        spin.setPrefix("Frame ")
        dlg_layout.addWidget(spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            idx = spin.value() - 1
            self._capture.select_frame(idx)
            self.set_capture_enabled(False)
            self._refresh(force_details=True)

    def _on_filter_changed(self) -> None:
        """Rebuild ProfileFilter from search/device widgets and propagate."""
        text = self._search_edit.text().strip()
        device_text = self._device_combo.currentText()
        if device_text == "CPU":
            devices: frozenset[Device] = frozenset({Device.CPU})
        elif device_text == "GPU":
            devices = frozenset({Device.GPU})
        else:
            devices = frozenset(Device)
        self._profile_filter = ProfileFilter(text=text, devices=devices)
        self._hierarchy_widget.set_filter(self._profile_filter)
        self._timeline_widget.set_filter(self._profile_filter)

    @staticmethod
    def _fps_from_cadence(frames: list[FrameTimings], idx: int) -> float:
        # Use frame timestamp deltas to reflect real presented cadence rather
        # than render-duration-only estimates.
        if idx <= 0 or idx >= len(frames):
            return 0.0
        dt_s = frames[idx].frame_timestamp - frames[idx - 1].frame_timestamp
        if dt_s <= 1e-6:
            return 0.0
        return 1.0 / dt_s

    @staticmethod
    def _cadence_ms(frames: list[FrameTimings], idx: int) -> float:
        if idx <= 0 or idx >= len(frames):
            return 0.0
        dt_s = frames[idx].frame_timestamp - frames[idx - 1].frame_timestamp
        if dt_s <= 1e-6:
            return 0.0
        return dt_s * 1000.0

    @staticmethod
    def _frame_start_ts(frame: FrameTimings) -> float:
        ts = float(getattr(frame, "frame_start_timestamp", 0.0) or 0.0)
        if ts > 0.0:
            return ts
        end_ts = float(getattr(frame, "frame_end_timestamp", 0.0) or 0.0)
        if end_ts > 0.0:
            return max(0.0, end_ts - (float(frame.total_ms) / 1000.0))
        return max(0.0, float(frame.frame_timestamp) - (float(frame.total_ms) / 1000.0))

    @staticmethod
    def _frame_end_ts(frame: FrameTimings) -> float:
        ts = float(getattr(frame, "frame_end_timestamp", 0.0) or 0.0)
        if ts > 0.0:
            return ts
        return float(frame.frame_timestamp)

    @classmethod
    def _cadence_wait_ms(cls, frames: list[FrameTimings], idx: int) -> float:
        if idx <= 0 or idx >= len(frames):
            return 0.0
        prev_end = cls._frame_end_ts(frames[idx - 1])
        cur_start = cls._frame_start_ts(frames[idx])
        if prev_end <= 0.0 or cur_start <= 0.0:
            cadence = cls._cadence_ms(frames, idx)
            return max(0.0, cadence - float(frames[idx].total_ms))
        return max(0.0, (cur_start - prev_end) * 1000.0)

    @classmethod
    def _effective_frame_total_ms(cls, frames: list[FrameTimings], idx: int) -> float:
        frame = frames[idx]
        cadence_ms = cls._cadence_ms(frames, idx)
        if cadence_ms > 0.0:
            return max(float(frame.total_ms), cadence_ms)
        return float(frame.total_ms)

    @classmethod
    def _with_cadence_aligned_totals(
        cls,
        frames: list[FrameTimings],
    ) -> list[FrameTimings]:
        aligned: list[FrameTimings] = []
        for idx, frame in enumerate(frames):
            effective_total_ms = cls._effective_frame_total_ms(frames, idx)
            if abs(effective_total_ms - float(frame.total_ms)) <= 1e-6:
                aligned.append(frame)
                continue
            aligned.append(replace(frame, total_ms=effective_total_ms))
        return aligned

    def _refresh_replay(self, *, force_details: bool = False) -> None:
        """Refresh all views when in replay (loaded session) mode."""
        self._refresh_actions_tab()
        samples = self._capture.replay_samples()
        if not samples:
            self._status_badge.setText("REPLAY")
            self._status_badge.setStyleSheet(
                "background:#1a2a3a; color:#70b8ff; border:1px solid #2a5a8a; border-radius:3px;"
            )
            self._kpi_label.setText("replay — no frames loaded")
            self._frame_label.setText("frame --/-- | age -- ms")
            return

        state = self._capture.state()
        idx = max(0, min(state.selected_index, len(samples) - 1))
        sample = samples[idx]

        self._status_badge.setText("REPLAY")
        self._status_badge.setStyleSheet(
            "background:#1a2a3a; color:#70b8ff; border:1px solid #2a5a8a; border-radius:3px;"
        )
        self._kpi_label.setText(
            f"replay total {sample.wall_ms:6.2f} ms | frame {idx + 1}/{len(samples)}"
        )
        self._frame_label.setText(
            f"frame {idx + 1}/{len(samples)} | age replay")

        token = (idx, len(samples), sample.wall_ms)
        if not force_details and token == self._last_details_token:
            return
        self._last_details_token = token
        self._details_hint.setText(
            f"Replay mode: frame {idx + 1}/{len(samples)}")
        self._hierarchy_widget.set_frame_sample(sample)
        self._timeline_widget.set_frame_sample(sample)
        self._table.setRowCount(0)

    def _update_status_badge(self, total_ms: float) -> None:
        ratio = total_ms / max(self._budget_ms, 1e-6)
        if ratio < 0.8:
            self._status_badge.setText("OK")
            self._status_badge.setStyleSheet(
                "background:#1f3f24; color:#84f39b; border:1px solid #2f6f3e; border-radius:3px;"
            )
        elif ratio < 1.0:
            self._status_badge.setText("WARN")
            self._status_badge.setStyleSheet(
                "background:#3b3114; color:#ffd86a; border:1px solid #6b5a22; border-radius:3px;"
            )
        else:
            self._status_badge.setText("SLOW")
            self._status_badge.setStyleSheet(
                "background:#482020; color:#ff9696; border:1px solid #7a3333; border-radius:3px;"
            )

    def _check_emit_warning(
        self,
        frame: FrameTimings,
        *,
        frame_total_ms: float | None = None,
    ) -> None:
        res_frac = FrameProfileDetailsBuilder.residual_fraction(
            frame,
            frame_total_ms=frame_total_ms,
        )
        res_ms = FrameProfileDetailsBuilder.residual_ms(
            frame,
        )
        if res_frac >= 0.10 and res_ms >= 0.5:
            self.profiler_warning.emit(
                f"PROFILER: {res_frac * 100:.1f}% of frame time ({res_ms:.2f} ms) is unaccounted. "
                f"Add profiling hooks to identify missing stages."
            )

    def _populate_details(self, frame: FrameTimings, *, frame_total_ms: float) -> None:
        cadence_wait_ms: float | None = None
        if self._capture.state().selected_index >= 0:
            frames = self._capture.frames()
            idx = self._capture.state().selected_index
            if 0 <= idx < len(frames):
                cadence_wait_ms = self._cadence_wait_ms(frames, idx)
        rows = FrameProfileDetailsBuilder.build_rows(
            frame,
            frame_total_ms=frame_total_ms,
            cadence_wait_ms=cadence_wait_ms,
        )
        self._table.setRowCount(len(rows))
        denom = max(float(frame_total_ms), 1e-6)
        for r, (name, kind, z_str, ms, _pct) in enumerate(rows):
            pct = (float(ms) / denom) * 100.0
            # Heat-map each row by that stage's own duration.
            # Residual/warn rows get a distinct orange tint instead of the
            # gradient to make them immediately stand out.
            is_residual = kind in ("residual", "residual_warn")
            if is_residual:
                bg = QColor(_COLOR_RESIDUAL_WARN)
                bg.setAlpha(80 if kind == "residual_warn" else 48)
            else:
                color = self._gradient.map_ms(ms)
                bg = QColor(color)
                bg.setAlpha(72)
            row_items = [
                QTableWidgetItem(name),
                QTableWidgetItem(kind),
                QTableWidgetItem(z_str),
                QTableWidgetItem(f"{ms:.3f}"),
                QTableWidgetItem(f"{pct:.1f}"),
            ]
            for c, item in enumerate(row_items):
                item.setForeground(_COLOR_TEXT)
                item.setBackground(bg)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter
                    | (Qt.AlignmentFlag.AlignRight if c >= 3 else Qt.AlignmentFlag.AlignLeft)
                )
                self._table.setItem(r, c, item)

    def _refresh_actions_tab(self) -> None:
        revision = self._action_profiler.revision
        if revision == self._last_action_revision:
            return
        self._last_action_revision = revision
        self._actions_widget.set_data(
            stats=self._action_profiler.stats(),
            events=self._action_profiler.events(),
        )


class _PaintEventFilter(QObject):
    """Event filter that pushes ``FrameTimings`` after each ``Paint`` event.

    Resolution order for timings:

    1. ``canvas.last_frame_timings`` — present when the widget uses
       :class:`~lks_utils.gui_qt.qt_paint_profile_mixin.QtPaintProfileMixin`.
       The mixin patches ``total_ms`` with the full outer scope and
       auto-injects the ``"Qt GL compose/flush"`` stage.
    2. ``canvas.renderer.last_frame_timings`` — legacy path for widgets
       that manage their own timing but expose a ``renderer`` attribute.
    """

    def __init__(self, canvas: QWidget, profiler: QFrameProfilerWidget) -> None:
        super().__init__(canvas)
        self._canvas = canvas
        self._profiler = profiler

    @property
    def canvas(self) -> QWidget:
        return self._canvas

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._canvas and event.type() == QEvent.Type.Paint:
            # Primary: mixin provides last_frame_timings directly on the widget.
            timings = getattr(self._canvas, "last_frame_timings", None)
            # Fallback: legacy renderer attribute (no mixin).
            if timings is None:
                renderer = getattr(self._canvas, "renderer", None)
                if renderer is not None:
                    timings = getattr(renderer, "last_frame_timings", None)
            self._profiler.push(timings)
        return super().eventFilter(watched, event)


__all__ = ["QFrameProfilerWidget"]
