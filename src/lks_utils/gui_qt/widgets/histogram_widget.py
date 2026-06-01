"""QHistogramWidget — generic value-distribution histogram with overlay markers.

Reusable PySide6 widget that renders a histogram from a float32 NumPy array.
Supports:
- Configurable bin count, log-scale Y axis, fill/stroke colors.
- Named vertical overlay lines (e.g., midpoint, clip bounds) with color + label.
- Mouse hover displays bin value range and count.
- ``set_data(array)`` to update; ``add_marker(name, value, color, label)`` for overlays.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

_DEFAULT_BIN_COUNT: int = 256
_DEFAULT_FILL_COLOR: str = "#4488cc"
_DEFAULT_STROKE_COLOR: str = "#2266aa"
_MARGIN_LEFT: int = 6
_MARGIN_RIGHT: int = 6
_MARGIN_TOP: int = 14
_MARGIN_BOTTOM: int = 20


@dataclass
class HistogramMarker:
    """A named vertical overlay line on the histogram."""

    name: str
    """Unique identifier for the marker."""

    value: float
    """Data-space value where the line is drawn."""

    color: str = "#ff0000"
    """CSS-style hex color string."""

    label: str = ""
    """Short text drawn next to the line (empty = use *name*)."""

    line_width: int = 2
    """Pen width in pixels."""

    dash: bool = False
    """If True, draw as a dashed line."""


class QHistogramWidget(QWidget):
    """Lightweight histogram widget drawn with QPainter.

    Signals:
        marker_moved(str, float): Emitted when a marker is dragged.  Args are (marker_name, new_value).
    """

    marker_moved: Signal = Signal(str, float)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        bin_count: int = _DEFAULT_BIN_COUNT,
        log_scale: bool = False,
        fill_color: str = _DEFAULT_FILL_COLOR,
        stroke_color: str = _DEFAULT_STROKE_COLOR,
        min_height: int = 100,
    ) -> None:
        super().__init__(parent)
        self._bin_count: int = bin_count
        self._log_scale: bool = log_scale
        self._fill_color: QColor = QColor(fill_color)
        self._stroke_color: QColor = QColor(stroke_color)
        self._markers: dict[str, HistogramMarker] = {}

        # Histogram data
        self._counts: np.ndarray | None = None
        self._bin_edges: np.ndarray | None = None
        self._data_min: float = 0.0
        self._data_max: float = 1.0

        # Interaction state
        self._hover_bin: int | None = None
        self._dragging_marker: str | None = None

        self.setMinimumHeight(min_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_data(self, data: np.ndarray, *, data_range: tuple[float, float] | None = None) -> None:
        """Compute and display a histogram of *data*.

        Args:
            data: 1-D or N-D float array.  Flattened internally.
            data_range: Optional explicit (min, max) for bin edges.
                        If ``None``, derived from data.
        """
        flat = data.ravel().astype(np.float64)
        if flat.size == 0:
            self._counts = None
            self._bin_edges = None
            self.update()
            return

        if data_range is not None:
            self._data_min, self._data_max = float(
                data_range[0]), float(data_range[1])
        else:
            self._data_min, self._data_max = float(
                np.nanmin(flat)), float(np.nanmax(flat))

        if self._data_min >= self._data_max:
            self._data_max = self._data_min + 1e-6

        self._counts, self._bin_edges = np.histogram(
            flat, bins=self._bin_count, range=(self._data_min, self._data_max),
        )
        self.update()

    def clear_data(self) -> None:
        """Remove histogram data and repaint blank."""
        self._counts = None
        self._bin_edges = None
        self.update()

    def set_bin_count(self, count: int) -> None:
        """Change bin count.  Does not recompute — call ``set_data`` again."""
        self._bin_count = max(4, count)

    def set_log_scale(self, enabled: bool) -> None:
        """Toggle logarithmic Y axis."""
        self._log_scale = enabled
        self.update()

    # -- Marker API --------------------------------------------------------

    def add_marker(
        self,
        name: str,
        value: float,
        color: str = "#ff0000",
        label: str = "",
        *,
        line_width: int = 2,
        dash: bool = False,
    ) -> None:
        """Add or update a named vertical overlay marker."""
        self._markers[name] = HistogramMarker(
            name=name, value=value, color=color,
            label=label or name, line_width=line_width, dash=dash,
        )
        self.update()

    def remove_marker(self, name: str) -> None:
        """Remove marker by name."""
        self._markers.pop(name, None)
        self.update()

    def set_marker_value(self, name: str, value: float) -> None:
        """Update an existing marker's value."""
        if name in self._markers:
            self._markers[name].value = value
            self.update()

    def get_marker_value(self, name: str) -> float | None:
        """Return marker value or None if not found."""
        m = self._markers.get(name)
        return m.value if m else None

    def clear_markers(self) -> None:
        """Remove all markers."""
        self._markers.clear()
        self.update()

    # ------------------------------------------------------------------
    # Coordinate mapping
    # ------------------------------------------------------------------

    def _chart_rect(self) -> QRectF:
        """Return the drawing area rectangle (inside margins)."""
        w = self.width()
        h = self.height()
        return QRectF(
            _MARGIN_LEFT, _MARGIN_TOP,
            w - _MARGIN_LEFT - _MARGIN_RIGHT,
            h - _MARGIN_TOP - _MARGIN_BOTTOM,
        )

    def _value_to_x(self, value: float) -> float:
        """Map a data-space value to pixel X coordinate."""
        r = self._chart_rect()
        t = (value - self._data_min) / (self._data_max - self._data_min)
        return r.left() + t * r.width()

    def _x_to_value(self, x: float) -> float:
        """Map pixel X to data-space value."""
        r = self._chart_rect()
        t = (x - r.left()) / r.width()
        return self._data_min + t * (self._data_max - self._data_min)

    def _bin_at_x(self, x: float) -> int | None:
        """Return the bin index at pixel X, or None if outside chart."""
        if self._counts is None:
            return None
        r = self._chart_rect()
        if x < r.left() or x > r.right():
            return None
        t = (x - r.left()) / r.width()
        idx = int(t * len(self._counts))
        return max(0, min(idx, len(self._counts) - 1))

    def _marker_at_x(self, x: float, tolerance: float = 6.0) -> str | None:
        """Return the name of the marker closest to pixel X within tolerance."""
        best_name: str | None = None
        best_dist = tolerance + 1.0
        for name, m in self._markers.items():
            mx = self._value_to_x(m.value)
            dist = abs(x - mx)
            if dist < best_dist:
                best_dist = dist
                best_name = name
        return best_name if best_dist <= tolerance else None

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        """Render the histogram bars, markers, and hover highlight."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self._chart_rect()

        # Background
        painter.fillRect(self.rect(), QColor("#1e1e1e"))

        if self._counts is None or self._bin_edges is None:
            painter.setPen(QPen(QColor("#666666")))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            painter.end()
            return

        # Compute Y scale
        max_count = float(np.max(self._counts)) if np.max(
            self._counts) > 0 else 1.0
        if self._log_scale:
            max_y = float(np.log1p(max_count))
        else:
            max_y = max_count

        # Draw bars
        bar_width = rect.width() / len(self._counts)
        fill_brush = QBrush(self._fill_color)
        stroke_pen = QPen(self._stroke_color, 1)
        hover_brush = QBrush(QColor(self._fill_color.red(
        ), self._fill_color.green(), self._fill_color.blue(), 200))

        for i, count in enumerate(self._counts):
            if count == 0:
                continue
            y_val = float(np.log1p(count)) if self._log_scale else float(count)
            bar_height = (y_val / max_y) * rect.height()
            x = rect.left() + i * bar_width
            y = rect.bottom() - bar_height

            bar_rect = QRectF(x, y, bar_width, bar_height)
            if i == self._hover_bin:
                painter.setBrush(hover_brush)
            else:
                painter.setBrush(fill_brush)
            painter.setPen(stroke_pen)
            painter.drawRect(bar_rect)

        # Draw axis labels: min and max
        label_font = QFont()
        label_font.setPixelSize(10)
        painter.setFont(label_font)
        painter.setPen(QPen(QColor("#999999")))
        painter.drawText(
            QRectF(rect.left(), rect.bottom() + 2, 80, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            f"{self._data_min:.4g}",
        )
        painter.drawText(
            QRectF(rect.right() - 80, rect.bottom() + 2, 80, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"{self._data_max:.4g}",
        )

        # Draw markers
        for m in self._markers.values():
            mx = self._value_to_x(m.value)
            if mx < rect.left() or mx > rect.right():
                continue
            pen = QPen(QColor(m.color), m.line_width)
            if m.dash:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(mx, rect.top()),
                             QPointF(mx, rect.bottom()))

            # Label above
            painter.setPen(QPen(QColor(m.color)))
            painter.setFont(label_font)
            painter.drawText(
                QRectF(mx - 40, rect.top() - 13, 80, 13),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                m.label,
            )

        painter.end()

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handle hover tooltip and marker dragging."""
        x = event.position().x()

        if self._dragging_marker:
            new_val = self._x_to_value(x)
            new_val = max(self._data_min, min(new_val, self._data_max))
            self.set_marker_value(self._dragging_marker, new_val)
            self.marker_moved.emit(self._dragging_marker, new_val)
            return

        # Update hover bin
        old_hover = self._hover_bin
        self._hover_bin = self._bin_at_x(x)
        if self._hover_bin != old_hover:
            self.update()

        # Tooltip for hovered bin
        if self._hover_bin is not None and self._bin_edges is not None:
            lo = self._bin_edges[self._hover_bin]
            hi = self._bin_edges[self._hover_bin + 1]
            count = int(self._counts[self._hover_bin])  # type: ignore[index]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"[{lo:.4g}, {hi:.4g})\nCount: {count:,}",
                self,
            )

        # Cursor shape: arrow near markers, crosshair elsewhere
        marker = self._marker_at_x(x)
        if marker:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Start dragging a marker if clicked near one."""
        if event.button() == Qt.MouseButton.LeftButton:
            marker = self._marker_at_x(event.position().x())
            if marker:
                self._dragging_marker = marker
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Stop marker dragging."""
        if self._dragging_marker:
            self._dragging_marker = None
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event: Any) -> None:  # noqa: N802
        """Clear hover state when mouse leaves widget."""
        self._hover_bin = None
        self.update()
        super().leaveEvent(event)


__all__ = ["HistogramMarker", "QHistogramWidget"]
