"""QCurveEditorWidget — interactive 2-D spline curve editor for PySide6.

Provides a square canvas for editing a :class:`~lks_utils.curve.SplineCurve`
with the following interactions:

- **LMB click on empty space**: add a new control point.
- **LMB drag**: move the selected control point (or Bézier handle).
- **RMB click on point**: cycle the point's interpolation type
  (Linear → Bézier → B-Spline → Linear).
- **RMB click on empty space**: context menu with presets, flip transforms, and
  reset options.
- **Delete / Backspace** while a point is selected: removes it (endpoints
  protected).
- ``set_monotonic(True)`` switches to a
  :class:`~lks_utils.curve.MonotonicSplineCurve` that rejects loopback curves.

Signals:
    curve_changed(SplineCurve): emitted after any curve mutation.

Usage::

    widget = QCurveEditorWidget()
    widget.curve_changed.connect(my_callback)
    widget.set_curve(my_curve)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu, QSizePolicy, QWidget

from lks_utils.curve import (
    MonotonicSplineCurve,
    PRESET_NAMES,
    PointType,
    SplineCurve,
    SplinePoint,
    TangentMode,
    get_preset,
)

# ---------------------------------------------------------------------- #
# Visual constants                                                        #
# ---------------------------------------------------------------------- #
_BG = QColor(30, 30, 30)
_GRID = QColor(60, 60, 60)
_DIAGONAL = QColor(80, 80, 80)
_CURVE = QColor(200, 200, 80)
_POINT_FILL = QColor(200, 200, 80)
_POINT_SELECTED = QColor(255, 120, 40)
_HANDLE = QColor(150, 150, 200)
_HANDLE_LINE = QColor(100, 100, 150)
_HANDLE_AUTO = QColor(120, 220, 255)
_HANDLE_ALIGNED = QColor(180, 220, 140)
_HOVER_GLOW = QColor(255, 235, 120)
_GHOST_POINT = QColor(255, 255, 180, 110)
_PT_RADIUS = 6.0
_HANDLE_RADIUS = 4.0
_HIT_RADIUS = 10.0


class QCurveEditorWidget(QWidget):
    """A square interactive spline curve editor.

    Args:
        parent: Optional parent widget.
        monotonic: If True initializes with a
            :class:`~lks_utils.curve.MonotonicSplineCurve`.
    """

    curve_changed = Signal(object)  # SplineCurve

    def __init__(
        self,
        parent: QWidget | None = None,
        monotonic: bool = False,
    ) -> None:
        super().__init__(parent)
        self._monotonic: bool = monotonic
        self._curve: SplineCurve = (
            MonotonicSplineCurve() if monotonic else SplineCurve()
        )
        self._selected: int = -1          # index of selected control point
        # Drag state: ("point", pt_idx) | ("handle_in", pt_idx) | ("handle_out", pt_idx)
        self._drag: tuple[str, int] | None = None
        self._hover_point_idx: int = -1
        self._hover_handle: tuple[str, int] | None = None
        self._hover_curve: bool = False
        self._hover_pos: QPointF | None = None

        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setMouseTracking(True)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def get_curve(self) -> SplineCurve:
        """Return the current curve (caller should treat as read-only)."""
        return self._curve

    def set_curve(self, curve: SplineCurve) -> None:
        """Replace the displayed curve."""
        self._curve = curve
        self._monotonic = isinstance(curve, MonotonicSplineCurve)
        self._selected = -1
        self._drag = None
        self._hover_point_idx = -1
        self._hover_handle = None
        self._hover_curve = False
        self._hover_pos = None
        self.update()

    def set_monotonic(self, enabled: bool) -> None:
        """Switch between SplineCurve and MonotonicSplineCurve.

        Preserves existing points; converts in-place if monotonic is toggled.
        """
        if enabled == self._monotonic:
            return
        data = self._curve.to_dict()
        if enabled:
            self._curve = MonotonicSplineCurve.from_dict(data)
        else:
            self._curve = SplineCurve.from_dict(data)
        self._monotonic = enabled
        self.update()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the current curve to a JSON-safe dict."""
        return self._curve.to_dict()

    def from_dict(self, data: dict[str, Any]) -> None:
        """Load a curve from a serialized dict."""
        from lks_utils.curve.monotonic_spline_curve import is_monotonic_dict
        if is_monotonic_dict(data):
            self._curve = MonotonicSplineCurve.from_dict(data)
            self._monotonic = True
        else:
            self._curve = SplineCurve.from_dict(data)
            self._monotonic = False
        self._selected = -1
        self._drag = None
        self._hover_point_idx = -1
        self._hover_handle = None
        self._hover_curve = False
        self._hover_pos = None
        self.update()

    @staticmethod
    def _dist2(a: QPointF, b: QPointF) -> float:
        dx = a.x() - b.x()
        dy = a.y() - b.y()
        return dx * dx + dy * dy

    def _is_point_near_curve(self, pos: QPointF, threshold_px: float = 10.0) -> bool:
        """Return True if *pos* is near the current rendered curve polyline."""
        n_samples = max(96, int(self._canvas_rect().width() * 0.75))
        thresh2 = threshold_px * threshold_px
        for i in range(n_samples):
            x = i / max(1, n_samples - 1)
            cp = self._to_canvas(x, self._curve.evaluate(x))
            if self._dist2(cp, pos) <= thresh2:
                return True
        return False

    def _update_hover(self, pos: QPointF) -> None:
        """Refresh hover state for UI affordances."""
        self._hover_pos = pos
        self._hover_handle = self._hit_handle(pos)
        if self._hover_handle is not None:
            self._hover_point_idx = -1
            self._hover_curve = False
            self.update()
            return

        self._hover_point_idx = self._hit_point(pos)
        if self._hover_point_idx >= 0:
            self._hover_curve = False
            self.update()
            return

        r = self._canvas_rect()
        if r.contains(pos):
            self._hover_curve = self._is_point_near_curve(pos)
        else:
            self._hover_curve = False
        self.update()

    # ------------------------------------------------------------------ #
    # Coordinate mapping                                                   #
    # ------------------------------------------------------------------ #

    def _canvas_rect(self) -> QRectF:
        """The square drawing area with a small margin."""
        m = 16.0
        side = float(min(self.width(), self.height()) - 2 * m)
        x0 = (self.width() - side) / 2.0
        y0 = (self.height() - side) / 2.0
        return QRectF(x0, y0, side, side)

    def _to_canvas(self, x: float, y: float) -> QPointF:
        """Normalize [0,1] curve coordinates → widget pixel coordinates."""
        r = self._canvas_rect()
        return QPointF(r.left() + x * r.width(), r.bottom() - y * r.height())

    def _to_curve(self, pos: QPointF) -> tuple[float, float]:
        """Widget pixel coordinates → normalized [0,1] curve coordinates."""
        r = self._canvas_rect()
        x = (pos.x() - r.left()) / r.width()
        y = (r.bottom() - pos.y()) / r.height()
        return float(x), float(y)

    # ------------------------------------------------------------------ #
    # Hit-testing                                                          #
    # ------------------------------------------------------------------ #

    def _hit_point(self, pos: QPointF) -> int:
        """Return index of control point under pos, or -1."""
        for i, pt in enumerate(self._curve.points):
            cp = self._to_canvas(pt.x, pt.y)
            if (pos - cp).manhattanLength() < _HIT_RADIUS:
                return i
        return -1

    def _hit_handle(self, pos: QPointF) -> tuple[str, int] | None:
        """Return (kind, idx) if pos hits a Bézier handle, else None."""
        for i, pt in enumerate(self._curve.points):
            if pt.point_type != PointType.BEZIER:
                continue
            for which, handle in [("handle_out", pt.handle_out), ("handle_in", pt.handle_in)]:
                if handle is None:
                    continue
                hx = pt.x + handle[0]
                hy = pt.y + handle[1]
                cp = self._to_canvas(hx, hy)
                if (pos - cp).manhattanLength() < _HIT_RADIUS:
                    return which, i
        return None

    # ------------------------------------------------------------------ #
    # Mouse events                                                         #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()

        if event.button() == Qt.MouseButton.LeftButton:
            # Check handles first
            h = self._hit_handle(pos)
            if h is not None:
                self._drag = h
                return

            idx = self._hit_point(pos)
            if idx >= 0:
                self._selected = idx
                self._drag = ("point", idx)
                self.update()
                return

            # Click on empty space → add point
            cx, cy = self._to_curve(pos)
            if 0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0:
                new_idx = self._curve.add_point(cx, cy)
                self._selected = new_idx
                self._drag = ("point", new_idx)
                self.update()
                self.curve_changed.emit(self._curve)

        elif event.button() == Qt.MouseButton.RightButton:
            h = self._hit_handle(pos)
            if h is not None:
                which = "in" if h[0] == "handle_in" else "out"
                self._curve.cycle_tangent_mode(h[1], which)
                self.update()
                self.curve_changed.emit(self._curve)
                return
            idx = self._hit_point(pos)
            if idx >= 0:
                self._cycle_point_type(idx)
            else:
                self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            self._update_hover(event.position())
            return
        cx, cy = self._to_curve(event.position())
        kind = self._drag[0]
        idx = self._drag[1]

        if kind == "point":
            new_idx = self._curve.move_point(idx, cx, cy)
            if new_idx != idx:
                self._selected = new_idx
                self._drag = ("point", new_idx)
        elif kind in ("handle_in", "handle_out"):
            pt = self._curve.points[idx]
            dx = cx - pt.x
            dy = cy - pt.y
            self._curve.move_handle(
                idx, "in" if kind == "handle_in" else "out", dx, dy)

        self.update()
        self.curve_changed.emit(self._curve)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag = None

    def leaveEvent(self, event: Any) -> None:  # noqa: ANN001
        self._hover_point_idx = -1
        self._hover_handle = None
        self._hover_curve = False
        self._hover_pos = None
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ #
    # Keyboard events                                                      #
    # ------------------------------------------------------------------ #

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._selected > 0 and self._selected < len(self._curve.points) - 1:
                self._curve.remove_point(self._selected)
                self._selected = -1
                self.update()
                self.curve_changed.emit(self._curve)
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Context menu                                                         #
    # ------------------------------------------------------------------ #

    def _cycle_point_type(self, idx: int) -> None:
        """Cycle point type: LINEAR → BEZIER → BSPLINE → LINEAR."""
        cycle = [PointType.LINEAR, PointType.BEZIER, PointType.BSPLINE]
        current = self._curve.points[idx].point_type
        try:
            next_type = cycle[(cycle.index(current) + 1) % len(cycle)]
        except ValueError:
            next_type = PointType.LINEAR
        self._curve.set_point_type(idx, next_type)
        self.update()
        self.curve_changed.emit(self._curve)

    def _show_context_menu(self, global_pos: Any) -> None:
        menu = QMenu(self)

        # Preset submenu
        preset_menu = menu.addMenu("Presets")
        for name in PRESET_NAMES:
            action = preset_menu.addAction(name.replace("_", " ").title())
            action.setData(name)

        menu.addSeparator()
        flip_h = menu.addAction("Flip Horizontal")
        flip_v = menu.addAction("Flip Vertical")
        menu.addSeparator()
        reset_action = menu.addAction("Reset Curve")

        action = menu.exec(global_pos)
        if action is None:
            return

        if action.data() in PRESET_NAMES:
            preset_curve = get_preset(action.data())
            self.set_curve(preset_curve)
            self.curve_changed.emit(self._curve)
        elif action == flip_h:
            self._curve.flip_horizontal()
            self.update()
            self.curve_changed.emit(self._curve)
        elif action == flip_v:
            self._curve.flip_vertical()
            self.update()
            self.curve_changed.emit(self._curve)
        elif action == reset_action:
            self._curve.reset()
            self._selected = -1
            self.update()
            self.curve_changed.emit(self._curve)

    # ------------------------------------------------------------------ #
    # Painting                                                             #
    # ------------------------------------------------------------------ #

    def paintEvent(self, _event: Any) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._canvas_rect()

        # Background
        p.fillRect(self.rect(), _BG)
        p.fillRect(r, QColor(40, 40, 40))

        # Grid
        p.setPen(QPen(_GRID, 0.5))
        for i in range(1, 4):
            t = i / 4.0
            px = r.left() + t * r.width()
            py = r.top() + t * r.height()
            p.drawLine(QPointF(px, r.top()), QPointF(px, r.bottom()))
            p.drawLine(QPointF(r.left(), py), QPointF(r.right(), py))

        # Diagonal guide
        p.setPen(QPen(_DIAGONAL, 1.0, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))

        # Curve path
        n_samples = max(128, int(r.width()))
        curve_path = QPainterPath()
        pts_canvas = [
            self._to_canvas(x, self._curve.evaluate(x))
            for x in (i / (n_samples - 1) for i in range(n_samples))
        ]
        curve_path.moveTo(pts_canvas[0])
        for pt_c in pts_canvas[1:]:
            curve_path.lineTo(pt_c)
        if self._hover_curve:
            p.setPen(QPen(_HOVER_GLOW, 4.0))
            p.drawPath(curve_path)
        p.setPen(QPen(_CURVE, 1.5))
        p.drawPath(curve_path)

        # Bézier handle lines
        p.setPen(QPen(_HANDLE_LINE, 1.0, Qt.PenStyle.DashLine))
        for i, pt in enumerate(self._curve.points):
            if pt.point_type != PointType.BEZIER:
                continue
            pc = self._to_canvas(pt.x, pt.y)
            for handle in [pt.handle_out, pt.handle_in]:
                if handle is None:
                    continue
                hc = self._to_canvas(pt.x + handle[0], pt.y + handle[1])
                p.drawLine(pc, hc)

        # Bézier handles
        for i, pt in enumerate(self._curve.points):
            if pt.point_type != PointType.BEZIER:
                continue
            for which, handle, mode in [
                ("handle_out", pt.handle_out, pt.tangent_out_mode),
                ("handle_in", pt.handle_in, pt.tangent_in_mode),
            ]:
                if handle is None:
                    continue
                hc = self._to_canvas(pt.x + handle[0], pt.y + handle[1])
                is_hovered = self._hover_handle == (which, i)
                if mode == TangentMode.AUTO:
                    handle_color = _HANDLE_AUTO
                elif mode == TangentMode.ALIGNED:
                    handle_color = _HANDLE_ALIGNED
                else:
                    handle_color = _HANDLE
                if is_hovered:
                    p.setBrush(_HOVER_GLOW)
                    p.setPen(QPen(_HOVER_GLOW, 1.2))
                    p.drawEllipse(hc, _HANDLE_RADIUS + 2.5,
                                  _HANDLE_RADIUS + 2.5)
                p.setBrush(handle_color)
                p.setPen(QPen(handle_color, 1.0))
                p.drawEllipse(hc, _HANDLE_RADIUS, _HANDLE_RADIUS)

        # Control points
        for i, pt in enumerate(self._curve.points):
            pc = self._to_canvas(pt.x, pt.y)
            is_hovered = i == self._hover_point_idx
            color = _POINT_SELECTED if i == self._selected else _POINT_FILL
            if is_hovered and i != self._selected:
                p.setBrush(_HOVER_GLOW)
                p.setPen(QPen(_HOVER_GLOW, 1.2))
                p.drawEllipse(pc, _PT_RADIUS + 2.5, _PT_RADIUS + 2.5)
            p.setBrush(color)
            p.setPen(QPen(color.darker(150), 1.5))
            p.drawEllipse(pc, _PT_RADIUS, _PT_RADIUS)

        # Ghost insertion cue when hovering editable curve area.
        if (
            self._hover_pos is not None
            and self._hover_point_idx < 0
            and self._hover_handle is None
            and self._canvas_rect().contains(self._hover_pos)
        ):
            p.setBrush(_GHOST_POINT)
            p.setPen(QPen(_GHOST_POINT, 1.0, Qt.PenStyle.DashLine))
            p.drawEllipse(self._hover_pos, _PT_RADIUS - 1.0, _PT_RADIUS - 1.0)

        # Border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(90, 90, 90), 1.0))
        p.drawRect(r)

        p.end()

    def sizeHint(self) -> Any:
        from PySide6.QtCore import QSize
        return QSize(220, 220)


__all__ = ["QCurveEditorWidget"]
