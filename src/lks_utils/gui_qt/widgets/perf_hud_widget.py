"""Lightweight perf HUD widget — FPS, custom metrics, mini line graph.

A self-contained ``QWidget`` for overlaying live performance metrics on
any GUI. Designed to be cheap (zero work when hidden) and dependency-
free (just PySide6 + numpy).

Usage
-----
::

    from lks_utils.gui_qt.widgets.perf_hud_widget import PerfHudWidget

    hud = PerfHudWidget(parent=main_window)
    main_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,
                              QDockWidget("Perf", main_window).setWidget(hud))

    # Tick once per render frame.
    def on_paint():
        ...
        hud.tick_frame()

    # Register custom metrics — pulled lazily once per second.
    hud.add_metric("tiles", lambda: backend.resident_count)
    hud.add_metric("read ms", lambda: last_read_ms, graph=True)

    # Per-frame stage timings (drawn under a dedicated breakdown table).
    hud.add_stage("read", lambda: canvas.last_read_ms)
    hud.add_stage("overlays", lambda: canvas.last_overlays_ms)

    # One-shot timeline events (dropped onto the FPS graph as vertical
    # lines).
    canvas.stroke_began.connect(
        lambda: hud.mark_event("stroke begin", "#3cf"))
    canvas.stroke_ended.connect(
        lambda: hud.mark_event("stroke end", "#f63"))

The HUD samples FPS from :meth:`tick_frame` calls and graphed metrics
on a ~4 Hz timer. When :meth:`set_enabled` is False, the timer stops,
samplers run zero times, and the widget paints a single
"PROFILING DISABLED" banner so the user can confirm debug-rendering
overhead is gone.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

import numpy as np
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QClipboard, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

_FPS_WINDOW: Final[int] = 60
_GRAPH_HISTORY: Final[int] = 240
_DEFAULT_REFRESH_MS: Final[int] = 250
_DEFAULT_HISTORY_SECONDS: Final[int] = 15
_STAGE_HISTORY: Final[int] = 120
_EVENT_HISTORY: Final[int] = 64


@dataclass
class _Metric:
    name: str
    getter: Callable[[], float]
    graph: bool = False
    fmt: str = "{:.1f}"
    history: deque[float] = field(default_factory=lambda: deque(
        maxlen=_GRAPH_HISTORY))
    last_value: float = 0.0

    def sample(self) -> None:
        try:
            v = float(self.getter())
        except Exception:  # noqa: BLE001
            v = float("nan")
        self.last_value = v
        if self.graph:
            self.history.append(v)


@dataclass
class _Stage:
    """Per-frame stage timer (in milliseconds)."""

    name: str
    getter: Callable[[], float]
    history: deque[float] = field(default_factory=lambda: deque(
        maxlen=_STAGE_HISTORY))
    last_value: float = 0.0

    def sample(self) -> None:
        try:
            v = float(self.getter())
        except Exception:  # noqa: BLE001
            v = float("nan")
        self.last_value = v
        self.history.append(v)

    def stats(self) -> tuple[float, float, float, float, float]:
        """Return ``(last, avg, p50, p95, max)`` over the rolling window."""
        arr = np.asarray(self.history, dtype=np.float32)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return self.last_value, 0.0, 0.0, 0.0, 0.0
        return (float(self.last_value),
                float(np.mean(finite)),
                float(np.percentile(finite, 50)),
                float(np.percentile(finite, 95)),
                float(np.max(finite)))


@dataclass
class _TimelineEvent:
    """Stamped one-shot event (drawn on the FPS graph as a vertical line)."""

    label: str
    color: QColor
    frame_index: int


class PerfHudWidget(QWidget):
    """Live FPS + metrics HUD with optional per-metric line graphs.

    Composed of (top to bottom):

    1. FPS row + FPS graph (with optional vertical event markers).
    2. Each registered metric's row (and graph if ``graph=True``).
    3. A copy-pastable text breakdown table of registered stages.
    4. A footer toolbar with "Profiling enabled" checkbox + Copy button.
    """

    def __init__(self,
                 parent: QWidget | None = None,
                 *,
                 refresh_ms: int = _DEFAULT_REFRESH_MS,
                 history_seconds: int = _DEFAULT_HISTORY_SECONDS) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMinimumSize(180, 150)

        self._refresh_ms: int = int(refresh_ms)
        self._history_seconds: int = max(2, int(history_seconds))
        self._fps_window_frames: int = _FPS_WINDOW
        self._frame_times: deque[float] = deque(maxlen=self._fps_window_frames)
        self._fps_history: deque[float] = deque(maxlen=self._fps_history_len())
        self._frame_ms_history: deque[float] = deque(
            maxlen=self._frame_ms_history_len())
        self._metrics: list[_Metric] = []
        self._stages: list[_Stage] = []
        self._events: deque[_TimelineEvent] = deque(maxlen=_EVENT_HISTORY)
        self._frame_index: int = 0
        self._enabled: bool = True

        self._last_tick: float = time.perf_counter()
        self._timer = QTimer(self)
        self._timer.setInterval(self._refresh_ms)
        self._timer.timeout.connect(self._on_refresh)
        self._timer.start()

        self._enable_cb = QCheckBox("Profiling enabled", self)
        self._enable_cb.setChecked(True)
        self._enable_cb.toggled.connect(self.set_enabled)
        self._copy_btn = QPushButton("Copy table", self)
        self._copy_btn.clicked.connect(self._copy_table_to_clipboard)
        self._window_label = QLabel("Window (s)", self)
        self._window_spin = QSpinBox(self)
        self._window_spin.setRange(2, 120)
        self._window_spin.setValue(self._history_seconds)
        self._window_spin.valueChanged.connect(self.set_history_window_seconds)
        self._table_view = QTextEdit(self)
        self._table_view.setReadOnly(True)
        self._table_view.setMinimumHeight(72)
        self._table_view.setMaximumHeight(140)
        self._table_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._table_view.setStyleSheet(
            "QTextEdit { background: #181818; color: #ddd; "
            "border: 1px solid #333; font-family: Consolas, monospace; "
            "font-size: 11px; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addStretch(1)
        layout.addWidget(self._table_view)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(self._enable_cb)
        controls.addSpacing(8)
        controls.addWidget(self._window_label)
        controls.addWidget(self._window_spin)
        controls.addStretch(1)
        controls.addWidget(self._copy_btn)
        layout.addLayout(controls)

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable all sampling + repaints.

        When False the refresh timer stops, the breakdown table
        freezes at its last value, and the widget paints a single
        "PROFILING DISABLED" banner so the user can confirm
        debug-rendering overhead is gone.
        """
        self._enabled = bool(enabled)
        if self._enabled:
            self._timer.start()
        else:
            self._timer.stop()
        if self._enable_cb.isChecked() != self._enabled:
            block = self._enable_cb.blockSignals(True)
            self._enable_cb.setChecked(self._enabled)
            self._enable_cb.blockSignals(block)
        self.update()

    def set_history_window_seconds(self, seconds: int) -> None:
        """Resize rolling graph windows to the last ``seconds`` seconds."""
        self._history_seconds = max(2, int(seconds))
        self._fps_history = self._resize_deque(
            self._fps_history, self._fps_history_len())
        self._frame_ms_history = self._resize_deque(
            self._frame_ms_history, self._frame_ms_history_len())
        self._events = self._resize_deque(
            self._events, max(_EVENT_HISTORY, self._history_seconds * 8))
        if self._window_spin.value() != self._history_seconds:
            block = self._window_spin.blockSignals(True)
            self._window_spin.setValue(self._history_seconds)
            self._window_spin.blockSignals(block)
        self.update()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def tick_frame(self) -> None:
        """Call once per rendered frame to feed the FPS estimator."""
        if not self._enabled:
            return
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        if 0.0 < dt < 1.0:
            self._frame_times.append(dt)
            self._frame_ms_history.append(dt * 1000.0)
        self._frame_index += 1

    @property
    def fps(self) -> float:
        if not self._frame_times:
            return 0.0
        avg = sum(self._frame_times) / len(self._frame_times)
        return 1.0 / avg if avg > 0 else 0.0

    def add_metric(self,
                   name: str,
                   getter: Callable[[], float],
                   *,
                   graph: bool = False,
                   fmt: str = "{:.1f}") -> None:
        """Register a metric. ``getter`` is sampled on the refresh timer."""
        self._metrics.append(_Metric(name=name, getter=getter,
                                     graph=graph, fmt=fmt))

    def remove_metric(self, name: str) -> None:
        self._metrics = [m for m in self._metrics if m.name != name]

    def clear_metrics(self) -> None:
        self._metrics.clear()

    def add_stage(self,
                  name: str,
                  getter: Callable[[], float]) -> None:
        """Register a per-frame stage timer (returns ms)."""
        self._stages.append(_Stage(name=name, getter=getter))

    def remove_stage(self, name: str) -> None:
        self._stages = [s for s in self._stages if s.name != name]

    def clear_stages(self) -> None:
        self._stages.clear()

    def mark_event(self, label: str, color: str = "#3cf") -> None:
        """Drop a vertical marker on the FPS graph at the next tick.

        ``label`` is shown in the breakdown panel's recent-events
        list. ``color`` is any QColor-compatible string. No-op when
        profiling is disabled.
        """
        if not self._enabled:
            return
        self._events.append(_TimelineEvent(
            label=label, color=QColor(color),
            frame_index=self._frame_index))

    def breakdown_text(self) -> str:
        """Return the current breakdown table as plain ASCII text."""
        fps_samples = np.asarray(self._fps_history, dtype=np.float32)
        fps_finite = fps_samples[np.isfinite(fps_samples)]
        frame_samples = np.asarray(self._frame_ms_history, dtype=np.float32)
        frame_finite = frame_samples[np.isfinite(frame_samples)]
        fps_p95 = float(np.percentile(fps_finite, 95)
                        ) if fps_finite.size else 0.0
        frame_p95 = float(np.percentile(frame_finite, 95)
                          ) if frame_finite.size else 0.0
        lines = [
            f"FPS {self.fps:.1f}",
            f"frame ms p95 {frame_p95:.2f}  fps p95 {fps_p95:.1f}",
            f"window {self._history_seconds}s",
            "",
            f"{'stage':<14} {'last':>7} {'avg':>7} {'p50':>7} "
            f"{'p95':>7} {'max':>7}",
            "-" * 55,
        ]
        for s in self._stages:
            last, avg, p50, p95, mx = s.stats()
            lines.append(
                f"{s.name[:14]:<14} {last:>7.2f} {avg:>7.2f} "
                f"{p50:>7.2f} {p95:>7.2f} {mx:>7.2f}")
        if self._events:
            lines.append("")
            lines.append("recent events:")
            for ev in list(self._events)[-12:]:
                lines.append(f"  {ev.label}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Refresh + paint                                                    #
    # ------------------------------------------------------------------ #

    def _on_refresh(self) -> None:
        if not self._enabled:
            return
        self._fps_history.append(self.fps)
        for m in self._metrics:
            m.sample()
        for s in self._stages:
            s.sample()
        self._table_view.setPlainText(self.breakdown_text())
        if self.isVisible():
            self.update()

    def _copy_table_to_clipboard(self) -> None:
        text = self.breakdown_text()
        cb: QClipboard = QApplication.clipboard()
        cb.setText(text)

    def sizeHint(self) -> QSize:
        graphs = 1 + sum(1 for m in self._metrics if m.graph)
        rows = len(self._metrics) + 1
        return QSize(220, max(250, rows * 14 + graphs * 34 + 160))

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.fillRect(self.rect(), QColor(20, 20, 20, 220))
        if not self._enabled:
            self._paint_disabled_banner(p)
            p.end()
            return
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        p.setFont(font)
        line_h = p.fontMetrics().height()
        x = 8
        bottom_reserve = (self._table_view.height()
                          + self._copy_btn.height() + 16)
        avail_w = self.width() - 2 * x
        y = line_h
        fps = self.fps
        color = self._fps_color(fps)
        p.setPen(color)
        p.drawText(QPoint(x, y), f"FPS  {fps:6.1f}")
        if self._frame_ms_history:
            p.setPen(QColor(170, 210, 255))
            p.drawText(
                QPoint(x + 140, y),
                f"frame ms  {self._frame_ms_history[-1]:6.2f}",
            )
        y += 4
        graph_h = 28
        fps_graph_rect = QRect(x, y, avail_w, graph_h)
        self._draw_graph(p, fps_graph_rect,
                         list(self._fps_history),
                         color=color, baseline=60.0)
        self._draw_event_markers(p, fps_graph_rect)
        y += graph_h + 6
        frame_graph_rect = QRect(x, y, avail_w, graph_h)
        self._draw_graph(
            p,
            frame_graph_rect,
            list(self._frame_ms_history),
            color=QColor(120, 190, 255),
            baseline=16.67,
        )
        self._draw_event_markers(p, frame_graph_rect)
        y += graph_h + 6
        for m in self._metrics:
            if y > self.height() - bottom_reserve - line_h:
                break
            p.setPen(QColor(220, 220, 220))
            try:
                value_str = m.fmt.format(m.last_value)
            except Exception:  # noqa: BLE001
                value_str = "?"
            p.drawText(QPoint(x, y + line_h - 2),
                       f"{m.name[:14]:<14} {value_str:>10}")
            y += line_h + 2
            if m.graph and m.history:
                if y + graph_h > self.height() - bottom_reserve:
                    break
                self._draw_graph(p, QRect(x, y, avail_w, graph_h),
                                 list(m.history),
                                 color=QColor(120, 200, 255),
                                 baseline=None)
                y += graph_h + 6
        p.end()

    def _fps_history_len(self) -> int:
        hz = max(1.0, 1000.0 / max(1, self._refresh_ms))
        return max(8, int(round(self._history_seconds * hz)))

    def _frame_ms_history_len(self) -> int:
        # Track up to 120 FPS for the selected window.
        return max(32, int(self._history_seconds * 120))

    @staticmethod
    def _resize_deque(values: deque, maxlen: int) -> deque:
        last_values = list(values)[-maxlen:]
        return deque(last_values, maxlen=maxlen)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _paint_disabled_banner(self, p: QPainter) -> None:
        font = QFont("Consolas", 14, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor(240, 130, 130))
        p.drawText(self.rect(),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   "\n\nPROFILING DISABLED\n\n"
                   "(no sampling, no graph repaints,\n"
                   "stages not measured)")

    def _draw_event_markers(self, p: QPainter, rect: QRect) -> None:
        """Vertical lines on the FPS graph for each recent event."""
        if not self._events or not self._fps_history:
            return
        span = max(1, len(self._fps_history))
        right_frame = self._frame_index
        left_frame = right_frame - span
        for ev in self._events:
            if ev.frame_index < left_frame:
                continue
            t = (ev.frame_index - left_frame) / max(1, span - 1)
            xi = int(rect.x() + 1 + t * (rect.width() - 2))
            pen = QPen(ev.color, 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(xi, rect.y() + 1, xi, rect.y() + rect.height() - 1)

    @staticmethod
    def _fps_color(fps: float) -> QColor:
        if fps >= 50:
            return QColor(120, 240, 120)
        if fps >= 30:
            return QColor(240, 220, 120)
        return QColor(240, 120, 120)

    def _draw_graph(self,
                    p: QPainter,
                    rect: QRect,
                    samples: list[float],
                    *,
                    color: QColor,
                    baseline: float | None) -> None:
        p.fillRect(rect, QColor(35, 35, 35, 180))
        p.setPen(QPen(QColor(60, 60, 60), 1))
        p.drawRect(rect)
        if not samples:
            return
        arr = np.asarray(samples, dtype=np.float32)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return
        lo = float(np.min(finite))
        hi = float(np.max(finite))
        if baseline is not None:
            hi = max(hi, baseline)
        span = max(1e-6, hi - lo)
        n = len(samples)
        w = rect.width() - 2
        h = rect.height() - 2
        x0 = rect.x() + 1
        y0 = rect.y() + 1
        if baseline is not None and lo <= baseline <= hi:
            by = int(y0 + h - (baseline - lo) / span * h)
            p.setPen(QPen(QColor(80, 80, 80), 1, Qt.PenStyle.DashLine))
            p.drawLine(x0, by, x0 + w, by)
        p.setPen(QPen(color, 1))
        prev: tuple[int, int] | None = None
        for i, v in enumerate(samples):
            if not np.isfinite(v):
                prev = None
                continue
            xi = int(x0 + (i / max(1, n - 1)) * w)
            yi = int(y0 + h - (v - lo) / span * h)
            if prev is not None:
                p.drawLine(prev[0], prev[1], xi, yi)
            prev = (xi, yi)
