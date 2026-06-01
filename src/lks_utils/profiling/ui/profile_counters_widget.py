"""QProfileCountersWidget — one mini-graph sparkline per CounterTrack.

Provides a scrollable vertical stack of compact sparkline widgets, each bound
to one :class:`~lks_utils.profiling.counter_track.CounterTrack`.  Hover events
are broadcast via *hover_index_changed* so multiple views can stay in sync.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QScrollArea, QSizePolicy, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from lks_utils.profiling.counter_track import CounterTrack


# ── Visual constants ──────────────────────────────────────────────────────────
_COLOR_BG = QColor(0x16, 0x16, 0x16)
_COLOR_GRID = QColor(0x2E, 0x2E, 0x2E)
_COLOR_LABEL_BG = QColor(0x22, 0x22, 0x22)
_COLOR_TEXT_DIM = QColor(0x99, 0x99, 0x99)
_COLOR_TEXT = QColor(0xCC, 0xCC, 0xCC)
_COLOR_TRACE = QColor(0x29, 0xB6, 0xF6)
_COLOR_FILL_TOP = QColor(0x29, 0xB6, 0xF6, 60)
_COLOR_FILL_BOT = QColor(0x29, 0xB6, 0xF6, 0)
_COLOR_HOVER = QColor(0x00, 0xE5, 0xFF, 160)
_COLOR_BUDGET = QColor(0xFF, 0xC1, 0x07)

_LABEL_HEIGHT: int = 16
_GRAPH_HEIGHT: int = 44
_ROW_HEIGHT: int = _LABEL_HEIGHT + _GRAPH_HEIGHT
_ROW_SPACING: int = 4
_FONT_MONO = QFont("Consolas", 8)


class _CounterMiniGraph(QWidget):
    """Single-track sparkline mini-graph with hover support.

    Signals:
        hover_sample(int): sample index under mouse (-1 when outside).
    """

    hover_sample = Signal(int)

    def __init__(
        self,
        track: CounterTrack,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._track = track
        self._budget: float | None = None
        self._hover_idx: int = -1
        self.setMinimumHeight(_ROW_HEIGHT)
        self.setMaximumHeight(_ROW_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.setMouseTracking(True)

    @property
    def track(self) -> CounterTrack:
        return self._track

    def set_budget(self, value: float | None) -> None:
        self._budget = value
        self.update()

    def set_hover_index(self, idx: int) -> None:
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(200, _ROW_HEIGHT)

    def mouseMoveEvent(self, event: object) -> None:
        samples = self._track.samples()
        n = len(samples)
        if n < 2:
            self.hover_sample.emit(-1)
            return
        gr = self._graph_rect()
        pos_x = getattr(event, "position", lambda: None)()
        if pos_x is None:
            return
        fx = float(pos_x.x())
        if fx < gr.left() or fx > gr.right():
            self.hover_sample.emit(-1)
            return
        frac = (fx - gr.left()) / max(gr.width(), 1)
        idx = min(int(frac * n), n - 1)
        self.hover_sample.emit(idx)

    def leaveEvent(self, event: object) -> None:
        self.hover_sample.emit(-1)

    def _graph_rect(self) -> QRectF:
        return QRectF(
            0.0,
            float(_LABEL_HEIGHT),
            float(self.width()),
            float(_GRAPH_HEIGHT),
        )

    def paintEvent(self, event: object) -> None:  # noqa: N802
        samples = self._track.samples()
        w, h = self.width(), self.height()
        gr = self._graph_rect()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # ── Background ────────────────────────────────────────────────────
        painter.fillRect(0, 0, w, _LABEL_HEIGHT, _COLOR_LABEL_BG)
        painter.fillRect(gr.toRect(), _COLOR_BG)

        # ── Label row ─────────────────────────────────────────────────────
        painter.setFont(_FONT_MONO)
        painter.setPen(QPen(_COLOR_TEXT))
        painter.drawText(
            QRectF(4, 0, w - 8, _LABEL_HEIGHT),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._track.name,
        )
        latest = self._track.latest
        if latest is not None:
            painter.setPen(QPen(_COLOR_TEXT_DIM))
            painter.drawText(
                QRectF(4, 0, w - 8, _LABEL_HEIGHT),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                f"{latest:.2f}",
            )

        n = len(samples)
        if n < 2:
            painter.end()
            return

        # ── Value range ───────────────────────────────────────────────────
        min_v = min(samples)
        max_v = max(samples)
        if max_v <= min_v:
            max_v = min_v + 1.0

        def _x(i: int) -> float:
            return gr.left() + (i / (n - 1)) * gr.width()

        def _y(v: float) -> float:
            frac = (v - min_v) / (max_v - min_v)
            return gr.bottom() - frac * gr.height() * 0.85 - 3.0

        # ── Horizontal grid line at mid ────────────────────────────────────
        pen_grid = QPen(_COLOR_GRID)
        pen_grid.setWidth(1)
        painter.setPen(pen_grid)
        mid_y = gr.center().y()
        painter.drawLine(QPointF(gr.left(), mid_y), QPointF(gr.right(), mid_y))

        # ── Budget line ───────────────────────────────────────────────────
        if self._budget is not None:
            pen_budget = QPen(_COLOR_BUDGET)
            pen_budget.setStyle(Qt.PenStyle.DashLine)
            pen_budget.setWidth(1)
            painter.setPen(pen_budget)
            by = _y(self._budget)
            if gr.top() <= by <= gr.bottom():
                painter.drawLine(
                    QPointF(gr.left(), by), QPointF(gr.right(), by)
                )

        # ── Fill under trace ─────────────────────────────────────────────
        fill_path = QPainterPath()
        fill_path.moveTo(_x(0), gr.bottom())
        for i, v in enumerate(samples):
            fill_path.lineTo(_x(i), _y(v))
        fill_path.lineTo(_x(n - 1), gr.bottom())
        fill_path.closeSubpath()

        grad = QLinearGradient(0, gr.top(), 0, gr.bottom())
        grad.setColorAt(0.0, _COLOR_FILL_TOP)
        grad.setColorAt(1.0, _COLOR_FILL_BOT)
        painter.fillPath(fill_path, grad)

        # ── Trace line ────────────────────────────────────────────────────
        pen_trace = QPen(_COLOR_TRACE)
        pen_trace.setWidthF(1.4)
        painter.setPen(pen_trace)
        path = QPainterPath()
        path.moveTo(_x(0), _y(samples[0]))
        for i in range(1, n):
            path.lineTo(_x(i), _y(samples[i]))
        painter.drawPath(path)

        # ── Hover cursor ──────────────────────────────────────────────────
        idx = self._hover_idx
        if 0 <= idx < n:
            hx = _x(idx)
            pen_hover = QPen(_COLOR_HOVER)
            pen_hover.setWidthF(1.2)
            painter.setPen(pen_hover)
            painter.drawLine(QPointF(hx, gr.top()), QPointF(hx, gr.bottom()))

        painter.end()


class QProfileCountersWidget(QWidget):
    """Scrollable stack of mini-graph sparklines, one per :class:`CounterTrack`.

    Usage::

        w = QProfileCountersWidget()
        w.set_tracks([CounterTrack("draw_calls"), CounterTrack("triangles")])

        # push new sample each frame:
        draw_calls_track.push(n_draws)
        triangles_track.push(n_tris)
        w.refresh()

    Signals:
        hover_index_changed(int): emitted when the user hovers over a sample
            column so external viewers can sync their frame cursor.
    """

    hover_index_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracks: list[CounterTrack] = []
        self._graphs: list[_CounterMiniGraph] = []
        self._budget_by_name: dict[str, float] = {}
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────

    def set_tracks(self, tracks: list[CounterTrack]) -> None:
        """Replace the visible counter set.  Rebuilds mini-graphs."""
        self._tracks = list(tracks)
        self._rebuild_graphs()

    def set_budget(self, track_name: str, value: float | None) -> None:
        """Set or clear a budget threshold for a named counter track."""
        if value is None:
            self._budget_by_name.pop(track_name, None)
        else:
            self._budget_by_name[track_name] = float(value)
        for g in self._graphs:
            if g.track.name == track_name:
                g.set_budget(value)

    def refresh(self) -> None:
        """Repaint all mini-graphs (call after pushing new samples)."""
        for g in self._graphs:
            g.update()

    def set_hover_index(self, idx: int) -> None:
        """Sync the hover cursor from an external source."""
        for g in self._graphs:
            g.set_hover_index(idx)

    # ── Internal ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: #161616; }"
        )

        self._container = QWidget()
        self._container.setStyleSheet("background: #161616;")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(_ROW_SPACING)
        self._container_layout.addStretch(1)

        scroll.setWidget(self._container)
        outer.addWidget(scroll)

    def _rebuild_graphs(self) -> None:
        # Remove old graph widgets
        for g in self._graphs:
            self._container_layout.removeWidget(g)
            g.setParent(None)
            g.deleteLater()
        self._graphs.clear()

        # Insert new graphs before the stretch
        stretch_idx = self._container_layout.count() - 1
        for track in self._tracks:
            g = _CounterMiniGraph(track, self._container)
            budget = self._budget_by_name.get(track.name)
            if budget is not None:
                g.set_budget(budget)
            g.hover_sample.connect(self._on_graph_hover)
            self._graphs.append(g)
            self._container_layout.insertWidget(stretch_idx, g)
            stretch_idx += 1

    def _on_graph_hover(self, idx: int) -> None:
        for g in self._graphs:
            g.set_hover_index(idx)
        self.hover_index_changed.emit(idx)


__all__ = ["QProfileCountersWidget"]
