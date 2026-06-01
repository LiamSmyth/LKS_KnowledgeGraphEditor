"""Fast live profile preview graph widget.

Designed for high-frequency updates where the graph should remain cheap to
paint and independent from slow detail inspection tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Sequence

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from lks_utils.profiling.ui.perf_gradient_mapper import PerfGradientMapper

if TYPE_CHECKING:
    from lks_utils.gui_qt.canvas2d.canvas2d_renderer import FrameTimings


_COLOR_BG = QColor(0x16, 0x16, 0x16)
_COLOR_GRID = QColor(0x2E, 0x2E, 0x2E)
_COLOR_BUDGET = QColor(0xFF, 0xC1, 0x07)
_COLOR_ITEMS = QColor(0x66, 0xBB, 0x6A)
_COLOR_OVERLAYS = QColor(0x29, 0xB6, 0xF6)
_COLOR_BACKGROUND = QColor(0x90, 0xA4, 0xAE)
_COLOR_OVER_BUDGET = QColor(0xEF, 0x53, 0x50)
_COLOR_SELECTED = QColor(0x64, 0xB5, 0xF6)
_COLOR_CURSOR = QColor(0x00, 0xE5, 0xFF)
_COLOR_TEXT = QColor(0xCC, 0xCC, 0xCC)
_COLOR_TRACE = QColor(0xE6, 0xEE, 0xF0)


@dataclass(frozen=True, slots=True)
class PreviewLayerSpec:
    """Legend and color for one strata layer."""

    key: str
    label: str
    color: QColor


@dataclass(frozen=True, slots=True)
class PreviewSample:
    """Normalized sample consumed by the preview graph renderer."""

    total_ms: float
    layers: tuple[float, ...]


def _default_layer_specs() -> tuple[PreviewLayerSpec, ...]:
    return (
        PreviewLayerSpec("background", "bg", QColor(_COLOR_BACKGROUND)),
        PreviewLayerSpec("items", "cpu", QColor(_COLOR_ITEMS)),
        PreviewLayerSpec("overlays", "gpu", QColor(_COLOR_OVERLAYS)),
    )


def _frame_timings_extractor(frame: FrameTimings) -> PreviewSample:
    overlays_ms = sum(x.duration_ms for x in frame.overlay_timings)
    return PreviewSample(
        total_ms=float(frame.total_ms),
        layers=(
            max(0.0, float(frame.background_ms)),
            max(0.0, float(frame.items_ms)),
            max(0.0, overlays_ms),
        ),
    )


class QProfilePreviewGraphWidget(QWidget):
    """Stacked frame-time preview for live profiling at native UI cadence.

    Emits:
        frame_selected(index): user clicked one frame column.
    """

    frame_selected = Signal(int)
    frame_scrubbed = Signal(int)

    # Height of the heat-ribbon strip drawn below the strata area.
    _RIBBON_H: int = 6

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._budget_ms: float = 16.6
        self._samples_raw: list[object] = []
        self._sample_extractor: Callable[[object],
                                         PreviewSample] = _frame_timings_extractor
        self._layer_specs: tuple[PreviewLayerSpec, ...] = _default_layer_specs(
        )
        self._selected_idx: int = -1
        self._live_idx: int = -1
        self._font = QFont("Consolas", 8)
        self._trace_font = QFont("Consolas", 7)
        self._scrub_enabled: bool = False
        self._drag_scrubbing: bool = False

    def set_budget_ms(self, budget_ms: float) -> None:
        self._budget_ms = max(float(budget_ms), 1e-6)
        self.update()

    def set_scrub_enabled(self, enabled: bool) -> None:
        self._scrub_enabled = bool(enabled)

    def set_extractor(
        self,
        extractor: Callable[[object], PreviewSample],
        layer_specs: Sequence[PreviewLayerSpec],
    ) -> None:
        """Swap profile source mapping so callers can reuse this widget broadly."""
        self._sample_extractor = extractor
        self._layer_specs = tuple(layer_specs)
        self.update()

    def set_samples(
        self,
        samples: list[object],
        *,
        selected_idx: int,
        live_idx: int,
    ) -> None:
        self._samples_raw = samples
        self._selected_idx = int(selected_idx)
        self._live_idx = int(live_idx)
        self.update()

    def set_frames(
        self,
        frames: list[FrameTimings],
        *,
        selected_idx: int,
        live_idx: int,
    ) -> None:
        """Backwards-compatible alias for existing rendering profiler callers."""
        self.set_samples(frames, selected_idx=selected_idx, live_idx=live_idx)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if not self._samples_raw:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        idx = self._index_from_x(float(event.position().x()))
        self._drag_scrubbing = True
        self.frame_selected.emit(idx)
        if self._scrub_enabled:
            self.frame_scrubbed.emit(idx)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if not self._drag_scrubbing or not self._scrub_enabled or not self._samples_raw:
            return
        idx = self._index_from_x(float(event.position().x()))
        self.frame_scrubbed.emit(idx)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001
        del event
        self._drag_scrubbing = False

    def _index_from_x(self, x: float) -> int:
        w = max(1, self.width())
        n = len(self._samples_raw)
        step = max(1.0, w / max(1, n))
        idx = int(x / step)
        return max(0, min(idx, n - 1))

    @staticmethod
    def _smooth_series(values: list[float]) -> list[float]:
        if len(values) < 3:
            return values[:]
        out: list[float] = []
        for idx, value in enumerate(values):
            left = values[idx - 1] if idx > 0 else value
            right = values[idx + 1] if idx + 1 < len(values) else value
            out.append((left + 2.0 * value + right) / 4.0)
        return out

    def _build_extracted_samples(self) -> list[PreviewSample]:
        extracted: list[PreviewSample] = []
        expected_layers = len(self._layer_specs)
        for raw in self._samples_raw:
            sample = self._sample_extractor(raw)
            layers = tuple(max(0.0, float(v)) for v in sample.layers)
            if len(layers) < expected_layers:
                layers = layers + (0.0,) * (expected_layers - len(layers))
            elif len(layers) > expected_layers:
                layers = layers[:expected_layers]
            extracted.append(
                PreviewSample(
                    total_ms=max(0.0, float(sample.total_ms)),
                    layers=layers,
                )
            )
        return extracted

    def _draw_strata_paths(
        self,
        p: QPainter,
        samples: list[PreviewSample],
        *,
        width_px: int,
        height_px: int,
        max_ms: float,
    ) -> None:
        n = len(samples)
        if n <= 0:
            return
        step = width_px / max(1, n)
        centers = [(idx + 0.5) * step for idx in range(n)]

        layer_values: list[list[float]] = [[] for _ in self._layer_specs]
        for sample in samples:
            for layer_idx, ms in enumerate(sample.layers):
                layer_values[layer_idx].append(ms)
        layer_values = [self._smooth_series(v) for v in layer_values]

        cum_lower = [0.0] * n
        for layer_idx, spec in enumerate(self._layer_specs):
            current = layer_values[layer_idx]
            cum_upper = [cum_lower[i] + current[i] for i in range(n)]
            upper_points = [
                QPointF(float(centers[i]), float(
                    height_px - (cum_upper[i] / max_ms) * height_px))
                for i in range(n)
            ]
            lower_points = [
                QPointF(float(centers[i]), float(
                    height_px - (cum_lower[i] / max_ms) * height_px))
                for i in range(n)
            ]

            path = QPainterPath()
            path.moveTo(upper_points[0])
            for point in upper_points[1:]:
                path.lineTo(point)
            for point in reversed(lower_points):
                path.lineTo(point)
            path.closeSubpath()

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(spec.color)
            p.drawPath(path)
            p.setPen(QPen(spec.color.lighter(145), 1))
            p.drawPolyline(upper_points)
            cum_lower = cum_upper

        if 0 <= self._selected_idx < n:
            x = self._selected_idx * step
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(100, 181, 246, 36))
            p.drawRect(QRectF(x, 0.0, max(1.0, step), float(height_px)))

    def _draw_heat_ribbon(
        self,
        p: QPainter,
        samples: list[PreviewSample],
        *,
        width_px: int,
        ribbon_y: float,
        ribbon_h: float,
    ) -> None:
        """Draw a per-column color ribbon using the perf heat ramp."""
        n = len(samples)
        if n <= 0 or ribbon_h < 1.0:
            return
        mapper = PerfGradientMapper(self._budget_ms)
        step = width_px / max(1, n)
        p.setPen(Qt.PenStyle.NoPen)
        for idx, sample in enumerate(samples):
            color = mapper.map_ms(sample.total_ms)
            x = float(idx * step)
            w_col = max(1.0, float((idx + 1) * step) - x)
            p.fillRect(QRectF(x, ribbon_y, w_col, ribbon_h), color)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        del event
        p = QPainter(self)
        p.fillRect(self.rect(), _COLOR_BG)
        samples = self._build_extracted_samples()
        if not samples:
            p.setPen(_COLOR_TEXT)
            p.setFont(self._font)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "no preview data")
            p.end()
            return

        w = max(1, self.width())
        ribbon_h = self._RIBBON_H
        label_h = 18
        h = max(1, self.height() - label_h - ribbon_h)
        n = len(samples)

        peak_ms = max(sample.total_ms for sample in samples)
        max_ms = max(self._budget_ms * 2.0, peak_ms * 1.12, 1e-6)
        budget_y = int(h - min(max(self._budget_ms / max_ms, 0.0), 1.0) * h)

        p.setPen(QPen(_COLOR_GRID, 1, Qt.PenStyle.DotLine))
        lane_h = max(10, h // 4)
        for lane in range(1, 4):
            y = h - lane * lane_h
            p.drawLine(0, y, w, y)

        p.setPen(QPen(_COLOR_GRID, 1, Qt.PenStyle.DashLine))
        p.drawLine(0, budget_y, w, budget_y)
        p.setPen(_COLOR_BUDGET)
        p.setFont(self._font)
        p.drawText(QPoint(3, max(10, budget_y - 2)),
                   f"{self._budget_ms:.1f}ms")

        self._draw_strata_paths(p, samples, width_px=w,
                                height_px=h, max_ms=max_ms)
        self._draw_heat_ribbon(p, samples, width_px=w,
                               ribbon_y=float(h), ribbon_h=float(ribbon_h))

        trace_points: list[QPointF] = []
        step = w / max(1, n)
        for idx, sample in enumerate(samples):
            x = float((idx + 0.5) * step)
            y = float(h - min(max(sample.total_ms / max_ms, 0.0), 1.0) * h)
            trace_points.append(QPointF(x, y))
            if sample.total_ms > self._budget_ms:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(_COLOR_OVER_BUDGET.red(
                ), _COLOR_OVER_BUDGET.green(), _COLOR_OVER_BUDGET.blue(), 80))
                p.drawRect(QRectF(x - 1.0, float(y), 2.0,
                           float(max(1, budget_y - y))))

        p.setPen(QPen(_COLOR_TRACE, 1))
        if len(trace_points) > 1:
            p.drawPolyline(trace_points)

        if 0 <= self._live_idx < n:
            live_x = int((self._live_idx + 0.5) * step)
            p.setPen(QPen(_COLOR_CURSOR, 2))
            p.drawLine(live_x, 0, live_x, h)

        selected = samples[self._selected_idx] if 0 <= self._selected_idx < n else samples[-1]
        labels = [f"{spec.label}:{selected.layers[idx]:.1f}" for idx,
                  spec in enumerate(self._layer_specs)]
        label_y = float(h + ribbon_h + 2)
        p.setPen(_COLOR_TEXT)
        p.setFont(self._trace_font)
        p.drawText(
            QRectF(4.0, label_y, float(max(1, w - 8)), 14.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"total {selected.total_ms:5.2f} ms  |  " + "  ".join(labels),
        )

        p.end()


__all__ = ["QProfilePreviewGraphWidget", "PreviewLayerSpec",
           "PreviewSample", "PerfGradientMapper"]
